import base64
import re
import urllib
import subprocess
import distutils.util
import json

import pingparsing

import mongoengine as me

from mongoengine import DoesNotExist, Q, BooleanField

from time import time

from libcloud.common.types import InvalidCredsError
from libcloud.utils.networking import is_private_subnet
from libcloud.dns.types import Provider as DnsProvider
from libcloud.dns.types import RecordType
from libcloud.dns.providers import get_driver as get_dns_driver

from mist.api.shell import Shell

from mist.api.exceptions import MistError
from mist.api.exceptions import RequiredParameterMissingError
from mist.api.exceptions import CloudNotFoundError

from mist.api.helpers import amqp_publish_user, search_parser
from mist.api.helpers import startsandendswith
from mist.api.helpers import dirty_cow, parse_os_release

from mist.api.clouds.models import Cloud
from mist.api.machines.models import Machine
from mist.api.users.models import User

from mist.api.tag.methods import get_tags_for_resource

from mist.api import config

import mist.api.clouds.models as cloud_models

import logging

logging.basicConfig(level=config.PY_LOG_LEVEL,
                    format=config.PY_LOG_FORMAT,
                    datefmt=config.PY_LOG_FORMAT_DATE)
log = logging.getLogger(__name__)


def connect_provider(cloud, **kwargs):
    """Establishes cloud connection using the credentials specified.

    Cloud is expected to be a cloud mongoengine model instance.

    """
    return cloud.ctl.compute.connect(**kwargs)


def ssh_command(owner, cloud_id, machine_id, host, command,
                key_id=None, username=None, password=None, port=22):
    """
    We initialize a Shell instant (for mist.api.shell).

    Autoconfigures shell and returns command's output as string.
    Raises MachineUnauthorizedError if it doesn't manage to connect.

    """
    # check if cloud exists
    Cloud.objects.get(owner=owner, id=cloud_id, deleted=None)

    shell = Shell(host)
    key_id, ssh_user = shell.autoconfigure(owner, cloud_id, machine_id,
                                           key_id, username, password, port)
    retval, output = shell.command(command)
    shell.disconnect()
    return output


def list_locations(owner, cloud_id, cached=False, extra=True):
    """List the locations of the specified cloud"""
    try:
        cloud = Cloud.objects.get(owner=owner, id=cloud_id)
    except Cloud.DoesNotExist:
        raise CloudNotFoundError()
    if cached:
        locations = cloud.ctl.compute.list_cached_locations()
    else:
        locations = cloud.ctl.compute.list_locations()
    return [location.as_dict(extra=extra) for location in locations]


def filter_list_locations(auth_context, cloud_id, locations=None, perm='read',
                          cached=False, extra=True):
    """Filter the locations of the specific cloud based on RBAC policy"""
    if locations is None:
        locations = list_locations(
            auth_context.owner, cloud_id, cached, extra=extra)
    if not auth_context.is_owner():
        allowed_resources = auth_context.get_allowed_resources(perm)
        if cloud_id not in allowed_resources['clouds']:
            return {'cloud_id': cloud_id, 'locations': []}
        for i in range(len(locations) - 1, -1, -1):
            if locations[i]['id'] not in allowed_resources['locations']:
                locations.pop(i)
    return locations


def list_projects(owner, cloud_id):
    """List projects for each account.
    Currently supported for Equinix Metal clouds. For other providers
    this returns an empty list
    """
    cloud = Cloud.objects.get(owner=owner, id=cloud_id, deleted=None)

    if cloud.ctl.provider in ['equinixmetal']:
        conn = connect_provider(cloud)
        projects = conn.ex_list_projects()
        ret = [{'id': project.id,
                'name': project.name,
                'extra': project.extra
                }
               for project in projects]
    else:
        ret = []

    return ret


def list_resource_groups(owner, cloud_id):
    """List resource groups for each account.
    Currently supported for Azure Arm. For other providers
    this returns an empty list
    """
    cloud = Cloud.objects.get(owner=owner, id=cloud_id, deleted=None)

    if cloud.ctl.provider in ['azure_arm']:
        conn = connect_provider(cloud)
        groups = conn.ex_list_resource_groups()
    else:
        groups = []

    ret = [{'id': group.id,
            'name': group.name,
            'extra': group.extra
            }
           for group in groups]
    return ret


def list_storage_pools(owner, cloud_id):
    """
    List storage pools for LXD containers.
    """

    cloud = Cloud.objects.get(owner=owner, id=cloud_id, deleted=None)

    if cloud.ctl.provider in ['lxd']:
        conn = connect_provider(cloud)
        storage_pools = conn.ex_list_storage_pools(detailed=False)
    else:
        storage_pools = []

    ret = [{'title': pool.name,
            'val': pool.name}
           for pool in storage_pools]
    return ret


def list_storage_accounts(owner, cloud_id):
    """List storage accounts for each account.
    Currently supported for Azure Arm. For other providers
    this returns an empty list
    """
    cloud = Cloud.objects.get(owner=owner, id=cloud_id, deleted=None)
    if cloud.ctl.provider in ['azure_arm']:
        conn = connect_provider(cloud)
        accounts = conn.ex_list_storage_accounts()
    else:
        return []

    storage_accounts = []
    resource_groups = conn.ex_list_resource_groups()
    for account in accounts:
        location_id = account.location
        location = None
        # FIXME: circular import
        from mist.api.clouds.models import CloudLocation
        try:
            location = CloudLocation.objects.get(external_id=location_id,
                                                 cloud=cloud)
        except CloudLocation.DoesNotExist:
            pass
        r_group_name = account.id.split('resourceGroups/')[1].split('/')[0]
        r_group_id = ''
        for resource_group in resource_groups:
            if resource_group.name == r_group_name:
                r_group_id = resource_group.id
                break
        storage_account = {'id': account.id,
                           'name': account.name,
                           'location': location.id if location else None,
                           'extra': account.extra,
                           'resource_group': r_group_id}
        storage_accounts.append(storage_account)

    return storage_accounts


# TODO deprecate this!
# We should decouple probe_ssh_only from ping.
# Use them as two separate functions instead & through dramatiq
def probe(owner, cloud_id, machine_id, host, key_id='', ssh_user=''):
    """Ping and SSH to machine and collect various metrics."""

    if not host:
        raise RequiredParameterMissingError('host')

    ping_res = ping(owner=owner, host=host)
    try:
        ret = probe_ssh_only(owner, cloud_id, machine_id, host,
                             key_id=key_id, ssh_user=ssh_user)
    except Exception as exc:
        log.error(exc)
        log.warning("SSH failed when probing, let's see what ping has to say.")
        ret = {}

    ret.update(ping_res)
    return ret


def probe_ssh_only(owner, cloud_id, machine_id, host, key_id='', ssh_user='',
                   shell=None):
    """Ping and SSH to machine and collect various metrics."""

    # run SSH commands
    command = (
        "echo \""
        "LC_NUMERIC=en_US.UTF-8 sudo -n uptime 2>&1|"
        "grep load|"
        "wc -l && "
        "echo -------- && "
        "LC_NUMERIC=en_US.UTF-8 uptime && "
        "echo -------- && "
        "if [ -f /proc/uptime ]; then cat /proc/uptime | cut -d' ' -f1; "
        "else expr `date '+%s'` - `sysctl kern.boottime | sed -En 's/[^0-9]*([0-9]+).*/\\1/p'`;"  # noqa
        "fi; "
        "echo -------- && "
        "if [ -f /proc/cpuinfo ]; then grep -c processor /proc/cpuinfo;"
        "else sysctl hw.ncpu | awk '{print $2}';"
        "fi;"
        "echo -------- && "
        "/sbin/ifconfig;"
        "echo -------- &&"
        "/bin/df -Pah;"
        "echo -------- &&"
        "uname -r ;"
        "echo -------- &&"
        "cat /etc/*release;"
        "echo --------"
        "\"|sh"  # In case there is a default shell other than bash/sh (ex csh)
    )

    if key_id:
        log.warn('probing with key %s' % key_id)

    if not shell:
        cmd_output = ssh_command(owner, cloud_id, machine_id,
                                 host, command, key_id=key_id)
    else:
        _, cmd_output = shell.command(command)
    cmd_output = [str(part).strip()
                  for part in cmd_output.replace('\r', '').split('--------')]
    log.warn(cmd_output)
    uptime_output = cmd_output[1]
    loadavg = re.split('load averages?: ', uptime_output)[1].split(', ')
    users = re.split(' users?', uptime_output)[0].split(', ')[-1].strip()
    uptime = cmd_output[2]
    cores = cmd_output[3]
    ips = re.findall(r'inet addr:(\S+)', cmd_output[4]) or \
        re.findall(r'inet (\S+)', cmd_output[4])
    m = re.findall(r'((?:[0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2})',
                   cmd_output[4])
    if '127.0.0.1' in ips:
        ips.remove('127.0.0.1')
    macs = {}
    for i in range(0, len(ips)):
        try:
            macs[ips[i]] = m[i]
        except IndexError:
            # in case of interfaces, such as VPN tunnels, with a dummy MAC addr
            continue
    pub_ips = find_public_ips(ips)
    priv_ips = [ip for ip in ips if ip not in pub_ips]

    kernel_version = cmd_output[6].replace("\n", "")
    os_release = cmd_output[7]
    os, os_version, distro = parse_os_release(os_release)

    return {
        'uptime': uptime,
        'loadavg': loadavg,
        'cores': cores,
        'users': users,
        'pub_ips': pub_ips,
        'priv_ips': priv_ips,
        'macs': macs,
        'df': cmd_output[5],
        'timestamp': time(),
        'kernel': kernel_version,
        'os': os,
        'os_version': os_version,
        'distro': distro,
        'dirty_cow': dirty_cow(os, os_version, kernel_version)
    }


def _ping_host(host, pkts=10):
    ping = subprocess.Popen(['ping', '-c', str(pkts), '-i', '0.4', '-W',
                             '1', '-q', host], stdout=subprocess.PIPE)
    ping_parser = pingparsing.PingParsing()
    output = ping.stdout.read()
    result = ping_parser.parse(output.decode().replace('pipe 8\n', ''))
    return result.as_dict()


def ping(owner, host, pkts=10):
    if config.HAS_VPN:
        from mist.vpn.methods import super_ping
        result = super_ping(owner=owner, host=host, pkts=pkts)
    else:
        result = _ping_host(host, pkts=pkts)

    # In both cases, the returned dict is formatted by pingparsing.

    # Rename keys.
    final = {}
    for key, newkey in (('packet_transmit', 'packets_tx'),
                        ('packet_receive', 'packets_rx'),
                        ('packet_duplicate_rate', 'packets_duplicate'),
                        ('packet_loss_rate', 'packets_loss'),
                        ('rtt_min', 'rtt_min'),
                        ('rtt_max', 'rtt_max'),
                        ('rtt_avg', 'rtt_avg'),
                        ('rtt_mdev', 'rtt_std')):
        if key in result:
            final[newkey] = result[key]
    return final


def find_public_ips(ips):
    public_ips = []
    for ip in ips:
        # is_private_subnet does not check for ipv6
        try:
            if not is_private_subnet(ip):
                public_ips.append(ip)
        except:
            pass
    return public_ips


def notify_admin(title, message="", team="all"):
    """ This will only work on a multi-user setup configured to send emails """
    from mist.api.helpers import send_email
    send_email(title, message,
               config.NOTIFICATION_EMAIL.get(team, config.NOTIFICATION_EMAIL))


def notify_user(owner, title, message="", email_notify=True, **kwargs):
    # Notify connected owner via amqp
    payload = {'title': title, 'message': message}
    payload.update(kwargs)
    if 'command' in kwargs:
        output = '%s\n' % kwargs['command']
        if 'output' in kwargs:
            if not isinstance(kwargs['output'], str):
                kwargs['output'] = kwargs['output'].decode('utf-8', 'ignore')
            output += '%s\n' % kwargs['output']
        if 'retval' in kwargs:
            output += 'returned with exit code %s.\n' % kwargs['retval']
        payload['output'] = output
    amqp_publish_user(owner, routing_key='notify', data=payload)

    body = message + '\n' if message else ''
    if 'cloud_id' in kwargs:
        cloud_id = kwargs['cloud_id']
        body += "Cloud:\n"
        try:
            cloud = Cloud.objects.get(owner=owner, id=cloud_id, deleted=None)
            cloud_title = cloud.title
        except DoesNotExist:
            cloud_title = ''
            cloud = ''
        if cloud_title:
            body += "  Name: %s\n" % cloud_title
        body += "  Id: %s\n" % cloud_id
        if 'machine_id' in kwargs:
            machine_id = kwargs['machine_id']
            body += "Machine:\n"
            if kwargs.get('machine_name'):
                name = kwargs['machine_name']
            else:
                try:
                    name = Machine.objects.get(cloud=cloud,
                                               machine_id=machine_id).name
                except DoesNotExist:
                    name = ''
            if name:
                body += "  Name: %s\n" % name
            title += " for machine %s" % (name or machine_id)
            body += "  Id: %s\n" % machine_id
    if 'error' in kwargs:
        error = kwargs['error']
        body += "Result: %s\n" % ('Success' if not error else 'Error')
        if error and error is not True:
            body += "Error: %s" % error
    if 'command' in kwargs:
        body += "Command: %s\n" % kwargs['command']
    if 'retval' in kwargs:
        body += "Return value: %s\n" % kwargs['retval']
    if 'duration' in kwargs:
        body += "Duration: %.2f secs\n" % kwargs['duration']
    if 'output' in kwargs:
        body += "Output: %s\n" % kwargs['output']

    if email_notify:
        from mist.api.helpers import send_email
        email = owner.email if hasattr(owner, 'email') else owner.get_email()
        send_email("[%s] %s" % (config.PORTAL_NAME, title), body, email)


def create_dns_a_record(owner, domain_name, ip_addr):
    """Will try to create DNS A record for specified domain name and IP addr.

    All clouds for which there is DNS support will be tried to see if the
    relevant zone exists.

    """

    # split domain_name in dot separated parts
    parts = [part for part in domain_name.split('.') if part]
    # find all possible domains for this domain name, longest first
    all_domains = {}
    for i in range(1, len(parts) - 1):
        host = '.'.join(parts[:i])
        domain = '.'.join(parts[i:]) + '.'
        all_domains[domain] = host
    if not all_domains:
        raise MistError("Couldn't extract a valid domain from '%s'."
                        % domain_name)

    # iterate over all clouds that can also be used as DNS providers
    providers = {}
    clouds = Cloud.objects(owner=owner)
    for cloud in clouds:
        if isinstance(cloud, cloud_models.AmazonCloud):
            provider = DnsProvider.ROUTE53
            creds = cloud.apikey, cloud.apisecret
        # TODO: add support for more providers
        # elif cloud.provider == Provider.LINODE:
        #    pass
        # elif cloud.provider == Provider.RACKSPACE:
        #    pass
        else:
            # no DNS support for this provider, skip
            continue
        if (provider, creds) in providers:
            # we have already checked this provider with these creds, skip
            continue

        try:
            conn = get_dns_driver(provider)(*creds)
            zones = conn.list_zones()
        except InvalidCredsError:
            log.error("Invalid creds for DNS provider %s.", provider)
            continue
        except Exception as exc:
            log.error("Error listing zones for DNS provider %s: %r",
                      provider, exc)
            continue

        # for each possible domain, starting with the longest match
        best_zone = None
        for domain in all_domains:
            for zone in zones:
                if zone.domain == domain:
                    log.info("Found zone '%s' in provider '%s'.",
                             domain, provider)
                    best_zone = zone
                    break
            if best_zone:
                break

        # add provider/creds combination to checked list, in case multiple
        # clouds for same provider with same creds exist
        providers[(provider, creds)] = best_zone

    best = None
    for provider, creds in providers:
        zone = providers[(provider, creds)]
        if zone is None:
            continue
        if best is None or len(zone.domain) > len(best[2].domain):
            best = provider, creds, zone

    if not best:
        raise MistError("No DNS zone matches specified domain name.")

    provider, creds, zone = best
    name = all_domains[zone.domain]
    log.info("Will use name %s and zone %s in provider %s.",
             name, zone.domain, provider)

    msg = ("Creating A record with name %s for %s in zone %s in %s"
           % (name, ip_addr, zone.domain, provider))
    try:
        record = zone.create_record(name, RecordType.A, ip_addr)
    except Exception as exc:
        raise MistError(msg + " failed: %r" % repr(exc))
    log.info(msg + " succeeded.")
    return record


def filter_resources_by_tags(resources, tags):
    if not tags:
        return resources
    filtered_ids = []
    for resource in resources:
        resource_tags = get_tags_for_resource(resource.owner, resource)
        if tags.items() <= resource_tags.items():
            filtered_ids.append(resource.id)
    return resources.filter(id__in=filtered_ids)


def list_resources(auth_context, resource_type, search='', cloud='', tags='',
                   only='', sort='', start=0, limit=100, deref='', at=''):
    """
    List resources of any type.

    Supports filtering, sorting, pagination. Enforces RBAC.

    Parameters:
        auth_context(AuthContext): The AuthContext of the user
            to list resources for.
        resource_type(str): One of Mist resources:
            cloud, bucket, machine, zone, record, script, key,
            schedule, network, subnet, volume, location, image,
            rule, size, team, template, stack, tunnel.
        search(str): The pattern to search for, can contain one or both of:
            a) key(field)-value pairs separated by one of the operators:
                :, =, >, <, <=, >=, !=
            b) a single value that will be set to resource_type's ID or name.
            Example:
            >>> 't2.nano cpus>1 ram>=1024'
        cloud(str): List resources from these clouds only,
            with the same pattern as `search`.
        tags(str or dict): List resources which satisfy these tags:
            Examples:
            >>> '{"dev": "", "server": "east"}'
            >>> 'dev,server=east'
        only(str): The fields to load from the resource_type's document,
            comma-seperated.
        sort(str): The field to order the query results by; field may be
            prefixed with “+” or a “-” to determine the ordering direction.
        start(int): The index of the first item to return.
        limit(int): Return up to this many items.
        deref(str):
        at(str): Return resources created at or before a specific datetime
            (irrespectively of deleted or missing_since status after it)

    Returns:
        tuple(A mongoengine QuerySet containing the objects found,
             the total number of items found)
    """
    from mist.api.helpers import get_resource_model
    from mist.api.clouds.models import CLOUDS
    resource_model = get_resource_model(resource_type)

    # Init query object
    if resource_type == 'rule':
        query = Q(owner_id=auth_context.org.id)
    elif hasattr(resource_model, 'owner'):
        query = Q(owner=auth_context.org)
    else:
        query = Q()

    if resource_type in ['cloud', 'key', 'script', 'template']:
        if at:
            query &= Q(created__lte=at)
            query &= Q(deleted=False) | Q(deleted__gte=at)
        else:
            query &= Q(deleted=False)
        if resource_type == 'cloud':
            query &= Q(enabled=True)
    elif resource_type in ['machine', 'cluster', 'network',
                           'volume', 'image', 'subnet',
                           'location', 'size']:
        if at:
            query &= Q(missing_since=None) | Q(missing_since__gte=at)
        else:
            query &= Q(missing_since=None)

    if cloud:
        clouds, _ = list_resources(
            auth_context, 'cloud', search=cloud, only='id'
        )
        query &= Q(cloud__in=clouds)

    # filter organizations
    # if user is not an admin
    # get only orgs that have user as member
    if resource_type in {'org', 'orgs'} and not (
            auth_context.user.role == 'Admin'):
        query = Q(members=auth_context.user)

    if resource_type in {'user', 'users'} and not auth_context.is_owner():
        query = Q(id__in=[auth_context.user.id])

    search = search or ''
    sort = sort or ''
    only = only or ''
    postfilters = []
    id_implicit = False
    # search filter contains space separated terms
    # if the term contains :,=,<,>,!=, <=, >= then assume key/value query
    # otherwise search for objects with id or name matching the term
    terms = search_parser(search)
    for term in terms:
        if ':' in term:
            k, v = term.split(':')
            mongo_operator = '' if startsandendswith(v, '"') else '__contains'
        elif '!=' in term:
            k, v = term.split('!=')
            mongo_operator = '__ne'
        elif '<=' in term:
            k, v = term.split('<=')
            mongo_operator = '__lte'
        elif '>=' in term:
            k, v = term.split('>=')
            mongo_operator = '__gte'
        elif '>' in term:
            k, v = term.split('>')
            mongo_operator = '__gt'
        elif '<' in term:
            k, v = term.split('<')
            mongo_operator = '__lt'
        elif '=' in term:
            k, v = term.split('=')
            mongo_operator = '' if startsandendswith(v, '"') else '__contains'
        # TODO: support OR keyword
        elif term.lower() in ['and', 'or'] or not term:
            continue
        else:
            id_implicit = True
            k, v = 'id', term
            mongo_operator = '' if startsandendswith(v, '"') else '__icontains'

        v = v.strip('"')
        attr = getattr(resource_model, k, None)
        if isinstance(attr, BooleanField):
            try:
                v = bool(distutils.util.strtobool(v))
            except ValueError:
                v = bool(v)

        if k == 'provider' and 'cloud' in resource_type:
            try:
                query &= Q(_cls=CLOUDS[v]()._cls)
            except KeyError:
                return Cloud.objects.none(), 0

        # TODO: only allow terms on indexed fields
        # TODO: support additional operators: >, <, !=, ~
        elif k == 'cloud':
            # exact match
            if not mongo_operator:
                resources, _ = list_resources(auth_context, k,
                                              search=f'"{v}"',
                                              only='id')
            else:
                resources, _ = list_resources(auth_context, k, search=v,
                                              only='id')
            query &= Q(**{f'{k}__in': resources})
        elif k == 'location':
            # exact match
            if not mongo_operator:
                resources, _ = list_resources(auth_context, k,
                                              search=f'"{v}"',
                                              only='id,location_type')
            else:
                resources, _ = list_resources(auth_context, k, search=v,
                                              only='id,location_type')
            # Also include the locations' children if any
            regions = resources.filter(location_type='region')
            locations = [zone.id for region in regions
                         for zone in region.children
                         if zone not in resources]
            locations += [resource.id for resource in resources]
            query &= Q(**{f'{k}__in': locations})
        elif k in ['owned_by', 'created_by']:
            if not v or v.lower() in ['none', 'nobody']:
                query &= Q(**{k: None})
                continue
            try:
                user = User.objects.get(
                    id__in=[m.id for m in auth_context.org.members],
                    email=v)
                query &= Q(**{k: user.id})
            except User.DoesNotExist:
                query &= Q(**{k: v})
        elif k in ['key_associations', ]:  # Looks like a postfilter
            postfilters.append((k, v))
        elif k == 'id':
            if id_implicit is True:
                implicit_query = Q(id=v)
                implicit_search_fields = {
                    'name', 'domain', 'title',
                    'email', 'first_name', 'last_name'}
                for field in implicit_search_fields:
                    if getattr(resource_model, field, None) and \
                            not isinstance(getattr(resource_model, field), property):  # noqa
                        implicit_query |= Q(**{
                            f'{field}{mongo_operator}': v})
                # id will always be exact match
                query &= implicit_query
            else:
                query &= Q(id=v)
        else:
            query &= Q(**{f'{k}{mongo_operator}': v})

    result = resource_model.objects(query)
    if only:
        only_list = [field for field in only.split(',')
                     if field in resource_model._fields]
        result = result.only(*only_list)

    for (k, v) in postfilters:
        if k == 'key_associations':
            from mist.api.machines.models import KeyMachineAssociation
            if not v or v.lower() in ['0', 'false', 'none']:
                ids = [machine.id for machine in result
                       if not KeyMachineAssociation.objects(
                           machine=machine).count()]
            elif v.lower() in ['sudo']:
                ids = [machine.id for machine in result
                       if KeyMachineAssociation.objects(
                           machine=machine, sudo=True).count()]
            elif v.lower() in ['root']:
                ids = [machine.id for machine in result
                       if KeyMachineAssociation.objects(
                           machine=machine, ssh_user='root').count()]
            else:
                ids = [machine.id for machine in result
                       if KeyMachineAssociation.objects(
                           machine=machine).count()]
            query &= Q(id__in=ids)
            result = resource_model.objects(query)

    try:
        if tags:
            if not isinstance(tags, dict):
                try:
                    tags = json.loads(tags)
                except json.JSONDecodeError:
                    tags = dict((key, value[0] if value else '')
                                for key, *value in (pair.split('=')
                                                    for pair in tags.split(
                                                        ',')))
            result = filter_resources_by_tags(result, tags)

        try:
            from mist.rbac.models import PERMISSIONS
        except ImportError:
            return result[start:start + limit], result.count()

        if result.count():
            if not auth_context.is_owner() \
                    and resource_type in PERMISSIONS.keys():
                # get_allowed_resources uses plural
                rtype = resource_type if resource_type.endswith(
                    's') else resource_type + 's'
                allowed_resources = auth_context.get_allowed_resources(
                    rtype=rtype)
                result = result.filter(id__in=allowed_resources)
            result = result.order_by(sort)
    except me.errors.InvalidQueryError:
        log.warn(f'Invalid query: {query}')
        return [], 0

    return result[start:start + limit], result.count()


def get_console_proxy_uri(auth_context, machine):
    if machine.cloud.ctl.provider == 'libvirt':
        import xml.etree.ElementTree as ET
        from html import unescape
        from datetime import datetime
        import hmac
        import hashlib
        xml_desc = unescape(machine.extra.get('xml_description', ''))
        root = ET.fromstring(xml_desc)
        console_type = 'serial'
        vnc_element_graphics = root.find('devices') \
            .find('graphics[@type="vnc"]')
        if vnc_element_graphics:
            console_type = "vnc"
            vnc_port = vnc_element_graphics.attrib.get('port')
            vnc_host = vnc_element_graphics.attrib.get('listen')
        if not vnc_element_graphics:
            vnc_element_serial = root.find('devices') \
                .find('console[@type="pty"]')
            if not vnc_element_serial:
                return None, None, 501, 'Action not supported'
        from mongoengine import Q
        from mist.api.machines.models import KeyMachineAssociation
        # Get key associations, prefer root or sudoer ones
        key_associations = KeyMachineAssociation.objects(
            Q(machine=machine.parent) & (Q(ssh_user='root') | Q(sudo=True))) \
            or KeyMachineAssociation.objects(machine=machine.parent)
        if not key_associations:
            return None, None, 403,\
                'You are not authorized to perform this action'
        key_id = key_associations[0].key.id
        host = '%s@%s:%d' % (key_associations[0].ssh_user,
                             machine.parent.hostname,
                             key_associations[0].port)
        expiry = int(datetime.now().timestamp()) + 100
        base_ws_uri = config.PORTAL_URI.replace('http', 'ws')
        if console_type == 'vnc':
            msg = '%s,%s,%s,%s,%s' % (host, key_id, vnc_host, vnc_port, expiry)
            mac = hmac.new(
                config.SECRET.encode(),
                msg=msg.encode(),
                digestmod=hashlib.sha256).hexdigest()
            proxy_uri = '%s/proxy/%s/%s/%s/%s/%s/%s' % (
                base_ws_uri, host, key_id, vnc_host, vnc_port, expiry, mac)
        elif console_type == 'serial':
            from mist.api.machines.methods import find_best_ssh_params
            parent_machine = machine.parent
            key_association_id, hostname, user, port = find_best_ssh_params(
                parent_machine, auth_context=auth_context)
            command = 'virsh console %s\n' % machine.name
            command_encoded = base64.b64encode(command.encode()).decode()
            msg = '%s,%s,%s,%s,%s,%s' % (user,
                                         hostname,
                                         port, key_association_id, expiry,
                                         command_encoded)
            mac = hmac.new(
                config.SECRET.encode(),
                msg=msg.encode(),
                digestmod=hashlib.sha256).hexdigest()
            proxy_uri = '%s/ssh/%s/%s/%s/%s/%s/%s/%s' % (
                base_ws_uri, user,
                hostname, port,
                key_association_id, expiry, mac, command_encoded)
        return proxy_uri, console_type, 200, None

    elif machine.cloud.ctl.provider == 'vsphere':
        console_type = 'vnc'
        console_uri = machine.cloud.ctl.compute.connection.ex_open_console(
            machine.machine_id)
        protocol, host = config.PORTAL_URI.split('://')
        protocol = protocol.replace('http', 'ws')
        params = urllib.parse.urlencode({'url': console_uri})
        proxy_uri = f"{protocol}://{host}/wsproxy/?{params}"
        return proxy_uri, console_type, 200, None

    raise NotImplementedError()
