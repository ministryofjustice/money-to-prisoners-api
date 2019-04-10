import pathlib
import shutil
import tempfile

from anymail.message import AnymailMessage
from django.conf import settings
from django.core.management import BaseCommand, call_command
from django.template import loader as template_loader
from django.utils.translation import gettext_lazy as _, activate, get_language
from mtp_common.tasks import default_from_address, prepare_context

from prison.models import PrisonerCreditNoticeEmail


class Command(BaseCommand):
    """
    Emails a PDF bundle of credit notices to prisons
    """
    help = __doc__.strip().splitlines()[0]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subject = _('These prisoners’ accounts have been credited')
        self.from_address = default_from_address()
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
                self.stderr.write('No email address found for %s' % prison)
            else:
                self.stderr.write('No known email addresses')
            return

        if not get_language():
            language = getattr(settings, 'LANGUAGE_CODE', 'en')
            activate(language)

        bundle_dir = pathlib.Path(tempfile.mkdtemp())
        try:
            for credit_notice_email in credit_notice_emails:
                path = bundle_dir / ('prison-credits-%s.pdf' % credit_notice_email.prison.nomis_id)
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
        if not path.exists():
            if self.verbosity:
                self.stdout.write('Nothing to send to %s' % credit_notice_email)
            return

        template_context = prepare_context()
        text_body = template_loader.get_template('credit/prisoner-notice-email.txt').render(template_context)
        html_body = template_loader.get_template('credit/prisoner-notice-email.html').render(template_context)
        email = AnymailMessage(
            subject=str(self.subject),
            body=text_body.strip('\n'),
            from_email=self.from_address,
            to=[credit_notice_email.email],
            tags=['prisoner-notice'],
        )
        email.attach_alternative(html_body, 'text/html')
        email.attach_file(str(path), mimetype='application/pdf')

        if self.verbosity:
            self.stdout.write('Sending prisoner notice email to %s' % credit_notice_email)
        email.send()
