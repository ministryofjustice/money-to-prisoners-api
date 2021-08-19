import textwrap

from mtp_common.notify.templates import NotifyTemplateRegistry


class ApiNotifyTemplates(NotifyTemplateRegistry):
    """
    Templates that mtp-api expects to exist in GOV.UK Notify
    """
    templates = {
        'api-intel-notification-daily': {
            'subject': 'Your new intelligence tool notifications',
            'body': textwrap.dedent("""
                Dear ((name)),

                Here are your notifications for payment sources or prisoners you’re monitoring for ((date)).

                You have ((count)) notifications:
                ((notifications_url))

                ((notifications_text))

                You can turn off these email notifications from your settings screen in the intelligence tool.
                ((settings_url))

                Any feedback you can give us helps improve the tool further.
                ((feedback_url))

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'name',
                'count', 'date',
                'notifications_url', 'notifications_text',
                'settings_url', 'feedback_url',
            ],
        },
        'api-intel-notification-first': {
            'subject': 'New notification feature added to intelligence tool',
            'body': textwrap.dedent("""
                Dear ((name)),

                We’ve updated the prisoner money intelligence tool.

                At the moment, you can monitor payment sources or prisoners in one or many prisons.
                From today, we’ll notify you by daily email when any actions take place
                on a payment source or prisoner you’re monitoring.

                When there is no new activity, we won’t email you.

                View your notifications for payment sources or prisoners you’re monitoring for ((date)).

                You have ((count)) notifications:
                ((notifications_url))

                ((notifications_text))

                You can turn off these email notifications from your settings screen in the intelligence tool.
                ((settings_url))

                Any feedback you can give us helps improve the tool further.
                ((feedback_url))

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'name',
                'count', 'date',
                'notifications_url', 'notifications_text',
                'settings_url', 'feedback_url',
            ],
        },
        'api-intel-notification-not-monitoring': {
            'subject': 'New helpful ways to get the best from the intelligence tool',
            'body': textwrap.dedent("""
                Dear ((name)),

                We hope you already find the intelligence tool useful.
                At the moment, you’re not using the tool to ‘monitor’ payment sources
                or prisoners across prisons which can be useful in tracking potentially
                suspicious financial activity.
                You can start monitoring prisoners or payments sources from inside the tool anytime you like.

                And once you’ve started to monitor payment sources and/or prisoners,
                we’ll notify you by daily email when any actions take place.
                When there is no new activity on what you’re monitoring, we won’t email you.

                You can turn off these email notifications from your settings screen in the intelligence tool.
                ((settings_url))

                Any feedback you can give us helps improve the tool further.
                ((feedback_url))

                We hope you find this helpful.

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'name',
                'settings_url', 'feedback_url',
            ],
        },

        'api-notifications-report': {
            'subject': 'Prisoner money notifications for ((period_description))',
            'body': textwrap.dedent("""
                OFFICIAL SENSITIVE

                Use this link to download the prisoner money notifications report for ((period_description)).

                ((attachment))

                There is a separate sheet for each notification rule for credits and disbursements.

                The ‘Monitored by’ column that appears in some sheets is the number of
                users who are monitoring that prisoner or payment source.

                The ‘How many?’ column that appears in some sheets is the
                number that triggered the rule in column A. For example,
                if the ‘How many?’ column says 4 for the rule ‘More than 2 credits
                from the same debit card or bank account to any prisoner in a week’,
                then this means that a specific debit card or bank account
                sent 4 credits in a week up to when that credit was sent.

                If you have any queries, contact the team at ((team_email)).
            """).strip(),
            'personalisation': [
                'period_description', 'attachment', 'team_email',
            ],
        },

        'api-prisoner-notice-email': {
            'subject': 'These prisoners’ accounts have been credited',
            'body': textwrap.dedent("""
                Dear staff member,

                Use this link to download the credit slips for prisoners whose accounts
                have recently been digitally credited.
                ((attachment))

                Please print them out and deliver them confidentially to individuals’ cells.

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'attachment',
            ],
        },

        'api-new-account-requests': {
            'subject': 'You have new ((service_name)) users to approve',
            'body': textwrap.dedent("""
                Dear staff member,

                There are ((count)) users who have requested access to the ((service_name)).
                Log in to approve or reject them:
                ((login_url))

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'count',
                'service_name', 'login_url',
            ],
        },
        'api-account-locked': {
            'subject': 'Your ((service_name)) account is temporarily locked',
            'body': textwrap.dedent("""
                Dear ((name)),

                Your ((service_name)) password has been entered incorrectly
                too many times so your account is temporarily locked.

                After ((lockout_period)) minutes, you can reset your password by
                going to the log-in page and clicking ‘Forgotten your password?’.
                ((login_url))

                If urgent, your business hub manager can unlock your account.

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'name', 'lockout_period',
                'service_name', 'login_url',
            ],
        },
        'api-new-user': {
            'subject': 'Your new ((service_name)) account is ready to use',
            'body': textwrap.dedent("""
                Dear ((name)),

                Your new ((service_name)) account has been created for you.

                Username: ((username))
                Password: ((password))
                You can now sign in at: ((login_url))

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'name', 'username', 'password',
                'service_name', 'login_url',
            ],
        },
        'api-new-password': {
            'subject': 'Create a new ((service_name)) password',
            'body': textwrap.dedent("""
                Open the link below into your browser address bar to create your new ((service_name)) password.
                ((change_password_url))

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'service_name', 'change_password_url',
            ],
        },
        'api-reset-password': {
            'subject': 'Your new ((service_name)) password',
            'body': textwrap.dedent("""
                Your new ((service_name)) password has been created for you.

                Username: ((username))
                Password: ((password))

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'username', 'password',
                'service_name',
            ],
        },
        'api-user-moved': {
            'subject': 'Your new ((service_name)) account is ready to use',
            'body': textwrap.dedent("""
                Your account can now be used with the ((service_name)) service.

                Username: ((username))

                Your password remains the same.
                You can reset it from the login page if you need to.
                You can now sign in at: ((login_url))

                Kind regards,
                Prisoner money team
            """).strip(),
            'personalisation': [
                'username',
                'service_name', 'login_url',
            ],
        },
        'api-account-request-denied': {
            'subject': 'Account access for ((service_name)) was denied',
            'body': textwrap.dedent("""
                Your request to access ((service_name)) was denied.
            """).strip(),
            'personalisation': [
                'service_name',
            ],
        },
    }
