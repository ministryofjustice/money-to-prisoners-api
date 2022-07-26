from mtp_api.settings.base import *  # noqa

def callback_add_role_name(envelope):
    """ Callback function for opencensus """
    """ This configures cloud_RoleName """
    envelope.tags['ai.cloud.role'] = 'mtp-api-neil'
    envelope.tags['ai.cloud.roleInstance'] = 'mtp-api-neil'
    return True
