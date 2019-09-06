from user_event_log.models import UserEvent


def record_user_event(request, kind, data=None):
    """Records a user event in the database."""
    event = UserEvent(
        user=request.user,
        kind=kind,
        api_url_path=request.path,
        data=data,
    )
    event.save()
    return event
