import logging
import pathlib
import shutil
import tempfile

from django.core.management import BaseCommand, call_command
from mtp_common.tasks import send_email
from notifications_python_client.utils import DOCUMENT_UPLOAD_SIZE_LIMIT as NOTIFY_UPLOAD_LIMIT

from credit.management.commands.create_prisoner_credit_notices import parsed_date_or_yesterday
from prison.models import PrisonerCreditNoticeEmail

logger = logging.getLogger('mtp')


class Command(BaseCommand):
    """
    Emails a PDF bundle of credit notices to prisons
    """
    help = __doc__.strip().splitlines()[0]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.verbosity = 1

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--prison', help='NOMIS id of prison, defaults to all prisons.')
        parser.add_argument('--date', help='Credited date, defaults to yesterday.')

    def handle(self, prison=None, date=None, **options):
        self.verbosity = options.get('verbosity', self.verbosity)

        if not prison:
            credit_notice_emails = PrisonerCreditNoticeEmail.objects.all()
        else:
            credit_notice_emails = PrisonerCreditNoticeEmail.objects.filter(prison=prison)
        if not credit_notice_emails.exists():
            if prison:
                self.stderr.write(f'No email address found for {prison}')
            else:
                self.stderr.write('No known email addresses')
            return

        bundle_dir = pathlib.Path(tempfile.mkdtemp())
        try:
            for credit_notice_email in credit_notice_emails:
                path = bundle_dir / f'prison-credits-{credit_notice_email.prison.nomis_id}.pdf'
                self.handle_prison(credit_notice_email, path, date, **options)
        finally:
            if bundle_dir.exists():
                shutil.rmtree(str(bundle_dir))

    def handle_prison(self, credit_notice_email, path, date, **options):
        call_command(
            'create_prisoner_credit_notices',
            path, credit_notice_email.prison.nomis_id,
            date=date, **options
        )
        date_reference = parsed_date_or_yesterday(date).strftime('%Y-%m-%d')
        if not path.exists():
            if self.verbosity:
                self.stdout.write(f'Nothing to send to {credit_notice_email}')
            return
        if path.stat().st_size >= NOTIFY_UPLOAD_LIMIT:
            error_message = (
                f'Cannot send prisoner notice email to {credit_notice_email} because the attachment is too big'
            )
            logger.error(error_message)
            self.stdout.write(error_message)
            return

        if self.verbosity:
            self.stdout.write(f'Sending prisoner notice email to {credit_notice_email}')
        send_email(
            template_name='api-prisoner-notice-email',
            to=credit_notice_email.email,
            personalisation={
                'attachment': path.read_bytes(),
            },
            reference=f'credit-notices-{date_reference}-{credit_notice_email.prison.nomis_id}',
            staff_email=True,
        )
