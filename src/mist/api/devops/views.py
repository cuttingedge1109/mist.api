from . import gl

from pyramid.response import Response
from mist.api.helpers import view_config


OK = Response("OK", 200)
BAD = Response("Bad Request", 400)


@view_config(route_name='api_v1_devops_projects',
             request_method='GET', renderer='json')
def list_projects(request):
    """
    Tags: projects
    ---
    List the projects
    """
    projects = gl.projects.list(iterator=True)
    projects_json = []
    for project in projects:
        projects_json.append(project.to_json())
    return projects_json


@view_config(route_name='api_v1_devops_pipelines',
             request_method='GET', renderer='json')
def list_pipelines(request):
    """
    Tags: pipelines
    ---
    List the piepelines
    """
    project_id = request.matchdict['project']
    project = gl.projects.get(project_id, lazy=True)
    # project.trigger_pipeline('main', trigger_token)

    pipelines = project.pipelines.list()

    pipelines_json = []
    for pipeline in pipelines:
        pipelines_json.append(pipeline.to_json())
    return pipelines_json


@view_config(route_name='api_v1_devops_pipelines',
             request_method='POST', renderer='json')
def trigger_pipeline(request):
    """
    Tags: pipelines
    ---
    Trigger a new pipeline
    :params project: Project id
    :params variables: Variable dict for pipeline run
    """
    project_id = request.matchdict['project']
    variables = request.matchdict['variables']
    project = gl.projects.get(project_id, lazy=True)

    trigger = project.triggers.create({'description': 'mytrigger'})

    pipeline = project.trigger_pipeline('main', trigger.token, variables=variables)
    return pipeline.to_json()


@view_config(route_name='api_v1_devops_pipeline',
             request_method='GET', renderer='json')
def get_pipeline(request):
    """
    Tags: pipelines
    ---
    Get a piepeline
    """
    project_id = request.matchdict['project']
    pipeline_id = request.matchdict['pipeline']
    project = gl.projects.get(project_id, lazy=True)
    pipeline = project.pipelines.get(pipeline_id)
    return pipeline.to_json()


@view_config(route_name='api_v1_devops_pipeline',
             request_method='DELETE', renderer='json')
def delete_pipeline(request):
    """
    Tags: pipelines
    ---
    Delete a piepeline
    """
    project_id = request.matchdict['project']
    pipeline_id = request.matchdict['pipeline']
    project = gl.projects.get(project_id, lazy=True)
    pipeline = project.pipelines.get(pipeline_id)
    pipeline.delete()

    return OK


@view_config(route_name='api_v1_devops_pipeline_retry',
             request_method='POST', renderer='json')
def retry_pipeline(request):
    """
    Tags: pipelines
    ---
    Retry a piepeline
    """
    project_id = request.matchdict['project']
    pipeline_id = request.matchdict['pipeline']
    project = gl.projects.get(project_id, lazy=True)
    pipeline = project.pipelines.get(pipeline_id)
    pipeline.retry()

    return OK


@view_config(route_name='api_v1_devops_pipeline_cancel',
             request_method='POST', renderer='json')
def cancel_pipeline(request):
    """
    Tags: pipelines
    ---
    Cancel a piepeline
    """
    project_id = request.matchdict['project']
    pipeline_id = request.matchdict['pipeline']
    project = gl.projects.get(project_id, lazy=True)
    pipeline = project.pipelines.get(pipeline_id)
    pipeline.cancel()

    return OK


############################################# Jobs 
@view_config(route_name='api_v1_devops_project_jobs',
             request_method='GET', renderer='json')
def list_project_jobs(request):
    """
    Tags: jobs
    ---
    List the all jobs in the project
    """
    project_id = request.matchdict['project']
    project = gl.projects.get(project_id, lazy=True)
    jobs = project.jobs.list()

    jobs_json = []
    for job in jobs:
        jobs_json.append(job.to_json())
    return jobs_json


@view_config(route_name='api_v1_devops_pipeline_jobs',
             request_method='GET', renderer='json')
def list_pipeline_jobs(request):
    """
    Tags: jobs
    ---
    List the jobs in the pipeline
    """
    project_id = request.matchdict['project']
    project = gl.projects.get(project_id, lazy=True)
    pipeline_id = request.matchdict['pipeline']
    pipeline = project.pipelines.get(pipeline_id)
    jobs = pipeline.jobs.list()

    jobs_json = []
    for job in jobs:
        jobs_json.append(job.to_json())
    return jobs_json


@view_config(route_name='api_v1_devops_job',
             request_method='GET', renderer='json')
def get_pipeline(request):
    """
    Tags: jobs
    ---
    Get a job
    """
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gl.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)

    return job.to_json()


@view_config(route_name='api_v1_devops_job_erase',
             request_method='POST', renderer='json')
def erase_pipeline(request):
    """
    Tags: jobs
    ---
    Erase a job
    """
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gl.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)
    job.erasae()

    return OK


@view_config(route_name='api_v1_devops_job_play',
             request_method='POST', renderer='json')
def play_pipeline(request):
    """
    Tags: jobs
    ---
    Play a job
    """
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gl.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)
    job.play()

    return OK


@view_config(route_name='api_v1_devops_job_retry',
             request_method='POST', renderer='json')
def retry_pipeline(request):
    """
    Tags: jobs
    ---
    Retry a job
    """
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gl.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)
    job.retry()

    return OK


@view_config(route_name='api_v1_devops_job_cancel',
             request_method='POST', renderer='json')
def cancel_pipeline(request):
    """
    Tags: jobs
    ---
    Cancel a job
    """
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gl.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)
    job.cancel()

    return OK


@view_config(route_name='api_v1_devops_job_trace',
             request_method='POST', renderer='json')
def trace_pipeline(request):
    """
    Tags: jobs
    ---
    Trace a job
    """
    project_id = request.matchdict['project']
    job_id = request.matchdict['job']
    project = gl.projects.get(project_id, lazy=True)
    job = project.jobs.get(job_id)
    return job.trace()
