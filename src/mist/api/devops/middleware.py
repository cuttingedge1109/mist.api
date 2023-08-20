# from pyramid.response import Response
import gitlab
import logging

from mist.api import config
from mist.api.devops.methods import get_scm_token
from mist.api.exceptions import ForbiddenError, UnauthorizedError
from pyramid.response import Response

GITLAB_SDK_DEBUG_MODE = True
log = logging.getLogger(__name__)
SCM_403_RES = Response("SCM token is out of permissions", 403)

def check_scm_token_middleware(handler):
    def middleware(request):
        token = get_scm_token(request)

        # Check if the user has SCM token registered
        if not token:
            # return Response("You have to register SCM token first. ", 403)
            raise ForbiddenError("You have to register SCM token first.")

        gl = gitlab.Gitlab(url=config.GITLAB_SERVER, private_token=token)

        if GITLAB_SDK_DEBUG_MODE:
            gl.enable_debug()

        try:
            gl.auth()
        except Exception as exc:
            log.error("Failed to auth gitlab server `%s`, reason: %r" % (config.GITLAB_SERVER, exc))
            raise UnauthorizedError("SCM token is incorrect.")

        # Set the gitlab client as a property of the request object
        request.gitlab_client = gl

        # Call the next handler in the chain
        try:
            res = handler(request)
        except gitlab.exceptions.GitlabHttpError as e:
            if e.response_code == 403:
                return SCM_403_RES
            else:
                # TODO(ce1109): Distinguish other error codes
                raise e
        return res

    return middleware

