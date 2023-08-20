import gitlab
import mongoengine as me
from pyramid.response import Response

from mist.api.auth.methods import user_from_request
from mist.api.helpers import params_from_request, view_config
from mist.api.devops.methods import (
    get_scm_token,
    get_project_id_list,
    get_pipelines,
    get_jobs,
    get_pipeline_schedules,
    get_default_branch,
)
from mist.api.devops.middleware import check_scm_token_middleware
from mist.api.devops.models import SCMToken

# from mist.api.exceptions import PolicyUnauthorizedError
# from mist.api.exceptions import BadRequestError, KeyParameterMissingError, NotFoundError
from mist.api.exceptions import RequiredParameterMissingError

import logging


log = logging.getLogger(__name__)

OK_RES = Response("OK", 200)
POST_OK_RES = Response("OK", 201)


############################################# Token
TOKEN_FIELD_MISSING_RES = Response("token field is missing", 400)
@view_config(route_name='api_v1_devops_token',
             request_method='GET', renderer='json')
def get_token(request):
    """
    Tags: tokens
    ---
    Get a token
    """
    token = get_scm_token(request)
    if token:
        return token
    return Response("token doesn't exist", 404)


@view_config(route_name='api_v1_devops_token',
             request_method='POST', renderer='json')
def create_token(request):
    """
    Tags: tokens
    ---
    Create a token
    """

    params = params_from_request(request)
    user = user_from_request(request)
    token = params.get('token', None)

    if not token:
        return Response("token field is missing", 400)

    try:
        # TODO(ce1109): Exception handling for duplicated user
        SCMToken(user=user, token=token).save()
        return POST_OK_RES
    except Exception as e:
        return Response(str(e), 500)


@view_config(route_name='api_v1_devops_token',
             request_method='PUT', renderer='json')
def update_token(request):
    """
    Tags: tokens
    ---
    Update a token
    """

    params = params_from_request(request)
    user = user_from_request(request)
    token = params.get('token', None)

    if not token:
        return Response("token field is missing", 400)

    try:
        obj = SCMToken.objects.get(user=user)
    except me.DoesNotExist:
        return Response("token doesn't exist", 404)
    if obj.token == token:
        return Response("token is same", 200)
    obj.save()
    return POST_OK_RES


############################################# Projects
@view_config(route_name='api_v1_devops_projects', request_method='GET',
             renderer='json')
@check_scm_token_middleware
def list_projects(request):
    """
    Tags: projects
    ---
    List the projects
    """

    gc = request.gitlab_client
    projects = gc.projects.list(iterator=True)
    projects_json = []
    for project in projects:
        projects_json.append(project.asdict())
    return projects_json


############################################# Pipelines
@view_config(route_name='api_v1_devops_pipelines',request_method='GET',
             renderer='json')
@check_scm_token_middleware
def list_pipelines(request):
    """
    Tags: pipelines
    ---
    List the piepelines
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    pipelines_json = []
    if project_id == "all":
        projects = get_project_id_list(gc)
        for project_id in projects:
            pipelines_json += get_pipelines(gc, project_id)
    else:
        pipelines_json = get_pipelines(gc, project_id)
    return pipelines_json


@view_config(route_name='api_v1_devops_pipelines', request_method='POST',
             renderer='json')
@check_scm_token_middleware
def trigger_pipeline(request):
    """
    Tags: pipelines
    ---
    Trigger a new pipeline
    :params project: Project id
    :params variables: Variable dict for pipeline run
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    variables = request.matchdict['variables']
    project = gc.projects.get(project_id, lazy=True)

    trigger = project.triggers.create({'description': 'mytrigger'})

    pipeline = project.trigger_pipeline('main', trigger.token, variables=variables)
    return pipeline.asdict()


@view_config(route_name='api_v1_devops_pipeline', request_method='GET',
             renderer='json')
@check_scm_token_middleware
def get_pipeline(request):
    """
    Tags: pipelines
    ---
    Get a piepeline
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    pipeline_id = request.matchdict['pipeline']
    project = gc.projects.get(project_id, lazy=True)
    pipeline = project.pipelines.get(pipeline_id)
    return pipeline.asdict()


@view_config(route_name='api_v1_devops_pipeline', request_method='DELETE',
             renderer='json')
@check_scm_token_middleware
def delete_pipeline(request):
    """
    Tags: pipelines
    ---
    Delete a piepeline
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    pipeline_id = request.matchdict['pipeline']
    project = gc.projects.get(project_id, lazy=True)
    pipeline = project.pipelines.get(pipeline_id)
    pipeline.delete()

    return OK_RES


@view_config(route_name='api_v1_devops_pipeline_retry', request_method='POST',
             renderer='json')
@check_scm_token_middleware
def retry_pipeline(request):
    """
    Tags: pipelines
    ---
    Retry a piepeline
    """
    gc = request.gitlab_client
    project_id = request.matchdict['project']
    pipeline_id = request.matchdict['pipeline']
    project = gc.projects.get(project_id, lazy=True)
    pipeline = project.pipelines.get(pipeline_id)
    pipeline.retry()
    return OK_RES


@view_config(route_name='api_v1_devops_pipeline_cancel', request_method='POST',
             renderer='json')
@check_scm_token_middleware
def cancel_pipeline(request):
    """
    Tags: pipelines
    ---
    Cancel a piepeline
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    pipeline_id = request.matchdict['pipeline']
    project = gc.projects.get(project_id, lazy=True)
    pipeline = project.pipelines.get(pipeline_id)
    pipeline.cancel()

    return OK_RES


############################################# Jobs 
@view_config(route_name='api_v1_devops_project_jobs', request_method='GET',
             renderer='json')
@check_scm_token_middleware
def list_project_jobs(request):
    """
    Tags: jobs
    ---
    List the all jobs in the project
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    
    jobs_json = []
    if project_id == "all":
        projects = get_project_id_list(gc)
        for project_id in projects:
            jobs_json += get_jobs(gc, project_id)
    else:
        jobs_json = get_jobs(gc, project_id)
    return jobs_json


@view_config(route_name='api_v1_devops_pipeline_jobs', request_method='GET',
             renderer='json')
@check_scm_token_middleware
def list_pipeline_jobs(request):
    """
    Tags: jobs
    ---
    List the jobs in the pipeline
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    project = gc.projects.get(project_id, lazy=True)
    pipeline_id = request.matchdict['pipeline']
    pipeline = project.pipelines.get(pipeline_id)
    jobs = pipeline.jobs.list()

    jobs_json = []
    for job in jobs:
        jobs_json.append(job.asdict())
    return jobs_json


@view_config(route_name='api_v1_devops_job', request_method='GET',
             renderer='json')
@check_scm_token_middleware
def get_job(request):
    """
    Tags: jobs
    ---
    Get a job
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gc.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)

    return job.asdict()


@view_config(route_name='api_v1_devops_job_erase', request_method='POST',
             renderer='json')
@check_scm_token_middleware
def erase_job(request):
    """
    Tags: jobs
    ---
    Erase a job
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gc.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)
    job.erasae()

    return OK_RES


@view_config(route_name='api_v1_devops_job_play', request_method='POST',
             renderer='json')
@check_scm_token_middleware
def play_job(request):
    """
    Tags: jobs
    ---
    Play a job
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gc.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)
    job.play()

    return OK_RES


@view_config(route_name='api_v1_devops_job_retry', request_method='POST',
             renderer='json')
@check_scm_token_middleware
def retry_job(request):
    """
    Tags: jobs
    ---
    Retry a job
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gc.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)
    job.retry()

    return OK_RES


@view_config(route_name='api_v1_devops_job_cancel', request_method='POST',
             renderer='json')
@check_scm_token_middleware
def cancel_job(request):
    """
    Tags: jobs
    ---
    Cancel a job
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gc.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)
    job.cancel()

    return OK_RES


@view_config(route_name='api_v1_devops_job_trace', request_method='POST',
             renderer='json')
@check_scm_token_middleware
def trace_pipeline(request):
    """
    Tags: jobs
    ---
    Trace a job
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gc.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)
    return job.trace()


############################################# Pipeline schedules
@view_config(route_name='api_v1_devops_pipeline_schedules',request_method='GET',
             renderer='json')
@check_scm_token_middleware
def list_pipeline_schedules(request):
    """
    Tags: pipeline_schedules
    ---
    List the piepeline schedules
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    schedules_json = []
    if project_id == "all":
        projects = get_project_id_list(gc)
        for project_id in projects:
            schedules_json += get_pipeline_schedules(gc, project_id)
    else:
        schedules_json = get_pipeline_schedules(gc, project_id)
    return schedules_json


@view_config(route_name='api_v1_devops_pipeline_schedules', request_method='POST',
             renderer='json')
@check_scm_token_middleware
def create_pipeline_schedule(request):
    """
    Tags: pipeline_schedules
    ---
    Create a pipeline schedule
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    project = gc.projects.get(project_id, lazy=True)

    params = params_from_request(request)
    ref = params.get('ref', get_default_branch(gc, project_id))
    desc = params.get('description', None)
    cron = params.get('cron', None)

    if not ref:
        raise RequiredParameterMissingError("Target branch or tag is not provided")

    if not desc:
        raise RequiredParameterMissingError("Description is not provided")

    if not cron:
        raise RequiredParameterMissingError("Interval pattern is not provided")

    schedule = project.pipelineschedules.create({
        'ref': ref, # 'main',
        'description': desc, # 'Daily test',
        'cron': cron # '0 1 * * *'
    })

    return schedule.asdict()


@view_config(route_name='api_v1_devops_pipeline_schedule', request_method='GET',
             renderer='json')
@check_scm_token_middleware
def get_pipeline_schedule(request):
    """
    Tags: pipeline_schedules
    ---
    Get a pipeline schedule
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    schedule_id = request.matchdict['schedule']
    project = gc.projects.get(project_id, lazy=True)
    schedule = project.pipelineschedules.get(schedule_id)

    return schedule.asdict()


@view_config(route_name='api_v1_devops_pipeline_schedule', request_method='PUT',
             renderer='json')
@check_scm_token_middleware
def update_pipeline_schedule(request):
    """
    Tags: pipeline_schedules
    ---
    Update a pipeline schedule
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    schedule_id = request.matchdict['schedule']
    project = gc.projects.get(project_id, lazy=True)
    schedule = project.pipelineschedules.get(schedule_id)

    params = params_from_request(request)
    ref = params.get('ref', get_default_branch(gc, project_id))
    desc = params.get('description', None)
    cron = params.get('cron', None)

    if not ref:
        schedule.ref = ref

    if not desc:
        schedule.desc = desc

    if not cron:
        schedule.cron = cron

    schedule.save()

    return schedule.asdict()


@view_config(route_name='api_v1_devops_pipeline_schedule', request_method='DELETE',
             renderer='json')
@check_scm_token_middleware
def delete_pipeline_schedule(request):
    """
    Tags: pipeline_schedules
    ---
    Delete a pipeline schedule
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    schedule_id = request.matchdict['schedule']
    project = gc.projects.get(project_id, lazy=True)
    schedule = project.pipelineschedules.get(schedule_id)
    schedule.delete()

    return OK_RES


@view_config(route_name='api_v1_devops_pipeline_schedule', request_method='POST',
             renderer='json')
@check_scm_token_middleware
def play_pipeline_schedule(request):
    """
    Tags: pipeline_schedules
    ---
    Play a pipeline schedule
    """

    gc = request.gitlab_client
    project_id = request.matchdict['project']
    schedule_id = request.matchdict['schedule']
    project = gc.projects.get(project_id, lazy=True)
    schedule = project.pipelineschedules.get(schedule_id)
    schedule.play()

    return POST_OK_RES
