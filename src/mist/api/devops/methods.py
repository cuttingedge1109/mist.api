import mongoengine as me

from mist.api.auth.methods import user_from_request
from mist.api.devops.models import SCMToken


def get_scm_token(request):
    """Get user's SCM token

    If a token was not registered/created yet, it returns None
    """

    user = user_from_request(request)
    try:
        obj = SCMToken.objects.get(user=user)
    except me.DoesNotExist:
        return None
    return obj.token

