import mongoengine as me

from mist.api.auth.methods import user_from_request
from mist.api.devops.models import SCMToken


def get_scm_token(request):
    """
    Get user's SCM token

    If a token was not registered/created yet, it returns None
    """

    user = user_from_request(request)
    try:
        obj = SCMToken.objects.get(user=user)
    except me.DoesNotExist:
        return None
    return obj.token


def get_project_id_list(gc):
    """
    Get the project id list

    Parameters:
        gc: gitlab client
    Returns:
        List of project ids
    """
    projects = gc.projects.list(iterator=True)
    res = []
    for project in projects:
        res.append(project.asdict()["id"])
    return res


def get_pipelines(gc, project_id):
    """Get pipeline object list of a specific project"""

    project = gc.projects.get(project_id, lazy=True)
    pipelines_json = []
    pipelines = project.pipelines.list()
    for pipeline in pipelines:
        pipelines_json.append(pipeline.asdict())
    return pipelines_json


def get_jobs(gc, project_id):
    """Get job object list of a specific project"""

    project = gc.projects.get(project_id, lazy=True)
    jobs = project.jobs.list()

    jobs_json = []
    for job in jobs:
        jobs_json.append(job.asdict())

    return jobs_json


def get_pipeline_schedules(gc, project_id):
    """Get pipeline schedule object list of a specific project"""

    project = gc.projects.get(project_id, lazy=True)
    schedules_json = []
    schedules = project.pipelineschedules.list()
    for schedule in schedules:
        schedules_json.append(schedule.asdict())
    return schedules_json


def get_default_branch(gc, project_id):
    """Get default branch"""

    project = gc.projects.get(project_id, lazy=True)
    branches = project.branches.list()
    for br in branches:
        if br.asdict()["default"] == True:
            return br.name
