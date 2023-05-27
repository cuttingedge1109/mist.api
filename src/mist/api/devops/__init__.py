import gitlab
import logging

from mist.api import config


GITLAB_SDK_DEBUG_MODE = True

log = logging.getLogger(__name__)
gl = gitlab.Gitlab(url=config.GITLAB_SERVER, private_token=config.GITLAB_PRIVATE_TOKEN)

if GITLAB_SDK_DEBUG_MODE:
    gl.enable_debug()

try:
    gl.auth()
except Exception as exc:
    log.error("Failed to auth gitlab server `%s`, reason: %r" % (
              config.GITLAB_SERVER, exc))
