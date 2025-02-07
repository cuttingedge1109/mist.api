"""Schedule entity model."""
import datetime
import logging
from uuid import uuid4

import mongoengine as me

from mist.api.helpers import rtype_to_classpath
from mist.api.tag.models import Tag
from mist.api.exceptions import BadRequestError
from mist.api.users.models import Organization
from mist.api.exceptions import ScheduleNameExistsError
from mist.api.exceptions import RequiredParameterMissingError
from mist.api.selectors.models import SelectorClassMixin
from mist.api.ownership.mixins import OwnershipMixin

log = logging.getLogger(__name__)

#: Authorized values for Interval.period
PERIODS = ('days', 'hours', 'minutes', 'seconds', 'microseconds')


class BaseScheduleType(me.EmbeddedDocument):
    """Abstract Base class used as a common interface
    for scheduler types. There are three different types
    for now: Interval, Crontab and OneOff
    """
    meta = {'allow_inheritance': True}

    @property
    def schedule(self):
        raise NotImplementedError()


class Interval(BaseScheduleType):
    meta = {'allow_inheritance': True}

    type = 'interval'
    every = me.IntField(min_value=0, default=0, required=True)
    period = me.StringField(choices=PERIODS)

    @property
    def period_singular(self):
        return self.period[:-1]

    def __unicode__(self):
        if self.every == 1:
            return 'Interval every {0.period_singular}'.format(self)
        return 'Interval every {0.every} {0.period}'.format(self)

    def as_dict(self):
        return {
            'every': self.every,
            'period': self.period
        }


class OneOff(Interval):
    type = 'one_off'
    entry = me.DateTimeField(required=True)

    def __unicode__(self):
        return 'OneOff date to run {0.entry}'.format(self)

    def as_dict(self):
        return {
            'entry': str(self.entry)
        }


class Reminder(OneOff):
    type = 'reminder'
    message = me.StringField()

    def as_dict(self):
        return {
            'message': self.message
        }


class Crontab(BaseScheduleType):
    type = 'crontab'

    minute = me.StringField(default='*', required=True)
    hour = me.StringField(default='*', required=True)
    day_of_week = me.StringField(default='*', required=True)
    day_of_month = me.StringField(default='*', required=True)
    month_of_year = me.StringField(default='*', required=True)

    def __unicode__(self):

        def rfield(x):
            return str(x).replace(' ', '') or '*'

        return 'Crontab {0} {1} {2} {3} {4} (m/h/dom/mon/dow)'.format(
            rfield(self.minute), rfield(self.hour),
            rfield(self.day_of_month), rfield(self.month_of_year),
            rfield(self.day_of_week),
        )

    def as_dict(self):
        return {
            'minute': self.minute,
            'hour': self.hour,
            'day_of_week': self.day_of_week,
            'day_of_month': self.day_of_month,
            'month_of_year': self.month_of_year
        }

    def as_cron(self):
        def rfield(x):
            return str(x).replace(' ', '') or '*'

        return '{0} {1} {2} {3} {4}'.format(
            rfield(self.minute), rfield(self.hour),
            rfield(self.day_of_month), rfield(self.month_of_year),
            rfield(self.day_of_week),
        )


class BaseTaskType(me.EmbeddedDocument):
    """Abstract Base class used as a common interface
    for scheduler's tasks types. Action and Script"""

    meta = {'allow_inheritance': True}

    @property
    def args(self):
        raise NotImplementedError()

    @property
    def kwargs(self):
        raise NotImplementedError()

    @property
    def task(self):
        raise NotImplementedError()


class ActionTask(BaseTaskType):
    action = me.StringField()

    @property
    def args(self):
        return self.action

    @property
    def kwargs(self):
        return {}

    @property
    def task(self):
        return 'mist.api.tasks.group_resources_actions'

    def __str__(self):
        return 'Action: %s' % self.action

    def as_dict(self):
        return {
            'action': self.action
        }


class ScriptTask(BaseTaskType):
    script_id = me.StringField()
    params = me.StringField()

    @property
    def args(self):
        return self.script_id

    @property
    def kwargs(self):
        return {'params': self.params}

    @property
    def task(self):
        return 'mist.api.tasks.group_run_script'

    def __str__(self):
        return 'Run script: %s' % self.script_id

    def as_dict(self):
        return {
            'script_id': self.script_id,
            'params': self.params
        }


class Schedule(OwnershipMixin, me.Document, SelectorClassMixin):
    """Abstract base class for every schedule attr mongoengine model.
    This model is based on celery periodic task and creates defines the fields
    common to all schedules of all types. For each different schedule type, a
    subclass should be created adding any schedule specific fields and methods.

     Documents of all Schedule subclasses will be stored on the same mongo
    collection.

    One can perform a query directly on Schedule to fetch all cloud types, like
    this:

        Schedule.objects(owner=owner).count()

    """

    meta = {
        'collection': 'schedules',
        'allow_inheritance': True,
        'indexes': [
            {
                'fields': ['owner', 'name', 'deleted'],
                'sparse': False,
                'unique': True,
                'cls': False,
            },
        ],
    }

    id = me.StringField(primary_key=True, default=lambda: uuid4().hex)
    name = me.StringField(required=True)
    description = me.StringField()
    deleted = me.DateTimeField()

    owner = me.ReferenceField(Organization, required=True,
                              reverse_delete_rule=me.CASCADE)

    # celery periodic task specific fields
    queue = me.StringField()
    exchange = me.StringField()
    routing_key = me.StringField()

    # mist specific fields
    schedule_type = me.EmbeddedDocumentField(BaseScheduleType, required=True)
    task_type = me.EmbeddedDocumentField(BaseTaskType, required=True)

    # celerybeat-mongo specific fields
    expires = me.DateTimeField()
    start_after = me.DateTimeField()
    task_enabled = me.BooleanField(default=False)
    run_immediately = me.BooleanField()
    last_run_at = me.DateTimeField()
    total_run_count = me.IntField(min_value=0, default=0)
    max_run_count = me.IntField(min_value=0, default=0)

    reminder = me.ReferenceField('Schedule', required=False,
                                 reverse_delete_rule=me.NULLIFY)

    no_changes = False

    def __init__(self, *args, **kwargs):
        # FIXME
        import mist.api.schedules.base
        super(Schedule, self).__init__(*args, **kwargs)
        self.ctl = mist.api.schedules.base.BaseController(self)

    @property
    def org(self):
        return self.owner

    @property
    def owner_id(self):
        # FIXME We should consider storing the owner id as a plain
        # string, instead of using a ReferenceField, to minimize
        # unintentional dereferencing. This is already happending
        # in case of mist.api.rules.models.Rule.
        return self.owner.id

    @classmethod
    def add(cls, auth_context, name, **kwargs):
        """Add schedule

        This is a class method, meaning that it is meant to be called on the
        class itself and not on an instance of the class.

        You're not meant to be calling this directly, but on a schedule class
        instead like this:

            schedule = Schedule.add(owner=owner, **kwargs)
        """
        owner = auth_context.owner

        if not name:
            raise RequiredParameterMissingError('name')
        if not owner or not isinstance(owner, Organization):
            raise BadRequestError('owner')
        resource_type = kwargs.pop('resource_type', 'machine').rstrip('s')
        if resource_type not in rtype_to_classpath:
            raise BadRequestError('resource_type')
        if Schedule.objects(owner=owner, name=name, deleted=None):
            raise ScheduleNameExistsError()
        schedule = cls(owner=owner, name=name,
                       resource_model_name=resource_type)
        schedule.ctl.set_auth_context(auth_context)
        schedule.ctl.add(**kwargs)
        schedule.assign_to(auth_context.user)
        return schedule

    @property
    def schedule(self):
        if self.schedule_type:
            return self.schedule_type.schedule
        else:
            raise Exception("must define interval, crontab, one_off schedule")

    @property
    def args(self):
        if self.resource_model_name == 'machine' or \
                self.resource_model_name == 'machines':
            ids = [machine.id for machine in self.get_resources() if
                   machine.state != 'terminated']
        else:
            ids = [resource.id for resource in self.get_resources()]
        fire_up = self.task_type.args
        return [self.owner.id, fire_up, self.name, ids]

    @property
    def kwargs(self):
        return self.task_type.kwargs

    @property
    def task(self):
        return self.task_type.task

    @property
    def enabled(self):
        if self.deleted:
            return False
        try:
            if not self.get_resources().count():
                return False
        except Exception as e:
            log.error('Error getting resources for schedule %s: %r' % (
                self.id, e))
            return False

        if self.expires and self.expires < datetime.datetime.now():
            return False
        if self.start_after and self.start_after < datetime.datetime.now():
            return False
        if self.max_run_count and (
            (self.total_run_count or 0) >= int(self.max_run_count)
        ):
            return False
        else:
            return self.task_enabled

    def __unicode__(self):
        fmt = '{0.name}: {{no schedule}}'
        if self.schedule_type:
            fmt = 'name: {0.name} type: {0.schedule_type._cls}'
        else:
            raise Exception("must define interval or crontab schedule")
        return fmt.format(self)

    def validate(self, clean=True):
        """
        Override mongoengine validate. We should validate crontab entry.
            Use crontab_parser for crontab expressions.
            The parser is a general purpose one, useful for parsing hours,
            minutes and day_of_week expressions.

            example for minutes:
                minutes = crontab_parser(60).parse('*/15')
                [0, 15, 30, 45]

        """
        if isinstance(self.schedule_type, Crontab):
            try:
                from apscheduler.triggers.cron import CronTrigger
                CronTrigger.from_crontab(self.schedule_type.as_cron())
            except ValueError as exc:
                raise me.ValidationError('Crontab validation failed: %s' % exc)

        super(Schedule, self).validate(clean=True)

    def clean(self):
        if self.resource_model_name not in rtype_to_classpath:
            self.resource_model_name = 'machine'

    def delete(self):
        if self.reminder:
            self.reminder.delete()
        super(Schedule, self).delete()
        Tag.objects(resource_id=self.id, resource_type='schedule').delete()
        self.owner.mapper.remove(self)
        if self.owned_by:
            self.owned_by.get_ownership_mapper(self.owner).remove(self)

    def as_dict(self):
        # Return a dict as it will be returned to the API

        last_run = '' if self.total_run_count == 0 else str(self.last_run_at)

        selectors = [selector.as_dict() for selector in self.selectors]

        sdict = {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'schedule': str(self.schedule_type),
            'schedule_type': self.schedule_type.type,
            'schedule_entry': self.schedule_type.as_dict(),
            'task_type': self.task_type.as_dict(),
            'expires': str(self.expires or ''),
            'start_after': str(self.start_after or ''),
            'task_enabled': self.task_enabled,
            'active': self.enabled,
            'run_immediately': self.run_immediately or '',
            'last_run_at': last_run,
            'total_run_count': self.total_run_count,
            'max_run_count': self.max_run_count,
            'selectors': selectors,
            'owned_by': self.owned_by.id if self.owned_by else '',
            'created_by': self.created_by.id if self.created_by else '',
        }

        return sdict
