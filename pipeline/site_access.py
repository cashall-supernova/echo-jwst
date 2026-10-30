"""Site service and updater credentials stay separate from the team login."""
import os


def site_headers(token, updater_token=None):
    headers = {'OAI-Sites-Authorization': 'Bearer ' + token}
    key = updater_token or os.environ.get('ECHO_UPDATER_TOKEN')
    if key:
        headers['X-Echo-Updater-Token'] = key
    return headers
