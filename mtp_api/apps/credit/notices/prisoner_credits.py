import codecs
import collections
import re

from django.utils.translation import gettext as _

from credit.notices import NoticeBundle, get_asset_path
from credit.notices.utils import render_security_box
from transaction.utils import format_amount

western_european = codecs.lookup('cp1252')  # characters supported by NTA font
re_invalid_name = re.compile(r'(\d{6})')
re_whitespace = re.compile(r'\s+')


def format_name(name, fallback):
    name = re_whitespace.sub(' ', (name or '').strip()).upper()
    if not name or re_invalid_name.search(name):
        # empty or looks like card number
        return fallback
    try:
        western_european.encode(name)
    except UnicodeEncodeError:
        # some characters cannot be printed
        return fallback
    return name


def format_disbursement_method(method):
    return {'bank_transfer': _('bank transfer'), 'cheque': _('cheque')}.get(method, _('unknown method'))


Update = collections.namedtuple('Update', 'symbol heading subheading messages')


class PrisonerCreditNoticeBundle(NoticeBundle):
    """
    Creates a bundle of notices to prisoners receiving credits
    """

    def __init__(self, prison, prisoners, date):
        """
        :param prison: only used in PDF title
        :param prisoners: iterable of (prisoner_name: str, prisoner_number: str,
            credits: typing.Sequence[Credit], disbursements: typing.Sequence[Disbursement])
        :param date: date credits were credited
        """
        super().__init__()
        self.prison = prison
        self.prisoners = prisoners
        self.human_date = date.strftime('%d %b %Y').lstrip('0')

    @property
    def title(self):
        return _('Prisoner money updates from %(date)s at %(prison)s') % {
            'date': self.human_date,
            'prison': self.prison,
        }

    def render_pages(self):
        for prisoner in self.prisoners:
            self.render_prisoner_pages(*prisoner)

    def render_prisoner_pages(self, name, number, location, credits_list, disbursements_list):
        updates = []
        if credits_list:
            updates.append(Update(
                '+',
                _('Money in'),
                _('You’ve been sent money online.') + ' ' + _('It’s gone into your private cash account.'),
                [
                    {
                        'label': format_amount(credit.amount, trim_empty_pence=False),
                        'message': _('from %(name)s') % {
                            'name': format_name(credit.sender_name,  fallback=_('unknown sender')),
                        }
                    }
                    for credit in credits_list
                ]
            ))
        if disbursements_list:
            updates.append(Update(
                '–',
                _('Money out'),
                _('These disbursement requests have been sent.') + ' ' + _('It takes about 7 working days.'),
                [
                    {
                        'label': format_amount(disbursement.amount, trim_empty_pence=False),
                        'message': _('to %(name)s by %(method)s') % {
                            'name': format_name('%s %s' % (disbursement.recipient_first_name,
                                                           disbursement.recipient_last_name),
                                                fallback=_('unknown recipient')),
                            'method': format_disbursement_method(disbursement.method),
                        }
                    }
                    for disbursement in disbursements_list
                ]
            ))
        while updates:
            self.render_base_template()
            self.render_header(name, number, location)
            self.render_prisoner_page(updates)
            self.canvas.showPage()

    def render_prisoner_page(self, updates):
        top = 222
        bottom = self.page_height - 6
        gutter = 12
        heading_height = 12
        heading_gap = 6
        text_height = 6

        while top < bottom - heading_height - text_height and updates:
            update = updates.pop(0)
            left = self.render_prisoner_page_heading(gutter, top, update)
            top += heading_height
            while top <= bottom - text_height and update.messages:
                message = update.messages.pop(0)
                self.change_font('NTA-Bold', 12)
                label_width = self.text_width(message['label'])
                self.draw_text(left, top, message['label'])
                self.change_font('NTA-Light', 12)
                message = ' ' + message['message']
                message = self.truncate_text_to_width(self.page_width - label_width - 2 * gutter, message)
                self.draw_text(left + label_width, top, message)
                top += text_height
            top += heading_gap
            if update.messages:
                updates.insert(0, update)

    def render_prisoner_page_heading(self, x, y, update: Update):
        radius = 3
        left = x + radius
        self.draw_circle(left, y + radius - 3.3, radius, stroke=0, fill=1)
        self.change_font('NTA-Bold', 14)
        self.canvas.setFillGray(1)
        self.draw_text(left, y + radius - 2.8, update.symbol, align='C')
        self.canvas.setFillGray(0)
        left += 5
        self.draw_text(left, y, update.heading)
        self.change_font('NTA-Light', 12)
        self.draw_text(left, y + 5, update.subheading)
        return left

    def render_header(self, name, number, location):
        top = 16
        gutter = 12

        date_label = _('Updates from %(date)s') % {'date': self.human_date}

        sub_heading = number
        if isinstance(location, dict):
            levels = location.get('levels')
            if levels:
                level_labels = {
                    'Wing': _('Wing'),
                    'Landing': _('Landing'),
                    'Cell': _('Cell'),
                }
                labels = [
                    (level_labels.get(level.get('type')), level.get('value'))
                    for level in levels
                ]
            else:
                labels = [(_('Location'), location.get('description'))]
            labels = filter(lambda label: label[0] and label[1], labels)
            labels = '    '.join(map(lambda label: ': '.join(label), labels))
            if labels:
                sub_heading += '    ' + labels

        self.change_font('NTA-Light', 12)
        date_label_width = self.text_width(date_label)
        name_width_allowance = self.page_width - date_label_width - gutter * 2 - 6
        baseline = 0.8
        self.change_font('NTA-Bold', 19)
        if self.text_width(name) > name_width_allowance:
            self.change_font('NTA-Bold', 17)
            baseline = 0.3
        name = self.truncate_text_to_width(name_width_allowance, name)
        self.draw_text(gutter, top, name)

        self.change_font('NTA-Light', 16)
        self.draw_text(gutter, top + 7, sub_heading)

        self.change_font('NTA-Light', 12)
        self.draw_text(self.page_width - gutter, top + baseline, date_label, align='R')

    def render_base_template(self):
        self.draw_image(get_asset_path('logo.png'), x=94.558, y=57, w=20.884, h=17.321)
        self.change_font('NTA-Light', 12)
        self.draw_text(105, 80, _('Prisoner money update'), align='C')

        self.change_font('NTA-Light', 8)
        fold_text = _('Confidential. Please fold & staple')
        fold_line_width = (self.page_width - self.text_width(fold_text) - 3) / 2

        def render_fold_line(y):
            self.draw_text(105, y, fold_text, align='C')
            self.draw_line(0, y, fold_line_width, y)
            self.draw_line(self.page_width - fold_line_width, y, self.page_width, y)

        render_fold_line(120)
        render_fold_line(209)
        security_lines = render_security_box(120, 209, self.page_width)
        self.draw_lines(security_lines)

        staple = get_asset_path('staple.png')
        self.canvas.setFillGray(1)
        self.canvas.saveState()
        self.canvas.scale(-1, 1)
        self.draw_rect(-11, 158.55, 4.8, 11.9, stroke=0, fill=1)
        self.draw_image(staple, x=-10, y=160.3, w=1.8, h=8.4)
        self.canvas.restoreState()
        self.draw_rect(199, 158.55, 4.8, 11.9, stroke=0, fill=1)
        self.draw_image(staple, x=200, y=160.3, w=1.8, h=8.4)
        self.canvas.setFillGray(0)


def create_sample():
    import argparse
    import collections
    import datetime

    import django
    from django.conf import settings

    if not settings.configured:
        settings.configure(APP='api', ENVIRONMENT='local', APP_GIT_COMMIT='unknown')
        django.setup()

    def generate_samples():
        Credit = collections.namedtuple('Credit', 'amount sender_name')
        Disbursement = collections.namedtuple('Disbursement', 'amount method recipient_first_name recipient_last_name')

        yield ('JILLY HALL', 'A1401AE', {
            'description': 'LEI-A-2-002',
            'levels': [
                {'type': 'Wing', 'value': 'A'},
                {'type': 'Landing', 'value': '2'},
                {'type': 'Cell', 'value': '002'}
            ],
        }, [], [])
        yield ('JILLY HALL', 'A1401AE', {
            'description': 'LEI-B-2-002',
            'levels': [
                {'type': 'Wing', 'value': 'B'},
                {'type': 'Landing', 'value': '2'},
                {'type': 'Cell', 'value': '002'}
            ],
        }, [
            Credit(2000, 'JORDAN MARSH'),
            Credit(3000, 'MRS J MARSH'),
        ], [])
        yield ('JILLY HALL', 'A1401AE', {
            'description': 'LEI-C-2-002',
            'levels': [
                {'type': 'Wing', 'value': 'C'},
                {'type': 'Landing', 'value': '2'},
                {'type': 'Cell', 'value': '002'}
            ],
        }, [], [
            Disbursement(10000, 'cheque', 'thomas', 'raymond'),
        ])
        yield ('JAMES HALLS', 'A1409AE', {
            'description': 'LEI-A-2-002',
            'levels': [
                {'type': 'Wing', 'value': 'A'},
                {'type': 'Landing', 'value': '2'},
                {'type': 'Cell', 'value': '002'}
            ],
        }, [
            Credit(3500, 'JORDAN MARSH'),
            Credit(4000, 'BRETT WILKINS'),
            Credit(2036000, 'SOMEBODY WITH A SURPRISINGLY-LONG-SURNAME'),
            Credit(10000, 'JORDAN MARSH'),
            Credit(1000, 'RICHARDSON JUSTIN'),
            Credit(10000, 'POWELL JADE'),
            Credit(1000, 'PAIGE BARTON'),
            Credit(5, 'X GREEN'),
            Credit(5000, 'GARRY CLARK GARRY CLARK'),
            Credit(5000, 'SIMPSON R'),
            Credit(5001, 'Gordon Ian'),
        ], [
            Disbursement(1000, 'cheque', 'Jordan', 'Marsh'),
        ])
        yield ('RICKY-LONG EXTREMELY-LONG-SURNAME-RIPPIN', 'A1234AA', {
            'description': 'LEI-B-1-002',
            'levels': [
                {'type': 'Wing', 'value': 'B'},
                {'type': 'Landing', 'value': '1'},
                {'type': 'Cell', 'value': '002'}
            ],
        }, [
            Credit(2036000, 'SOMEBODY WITH A SIMULATED VERY EXTREMELY LONG NAME-THAT-TRUNCATES'),
            Credit(3500, 'Amélie Poulain'),  # supported characters
            Credit(100000, 'علاء الدين'),  # unsupported characters
            Credit(1000, 'Ігор Игорь'),  # unsupported characters
        ], [
            Disbursement(1000, 'cheque', 'SOMEBODY WITH A SIMULATED', 'VERY EXTREMELY LONG SURNAME-THAT-TRUNCATES'),
            Disbursement(1000, 'bank_transfer', 'Joséphine', 'Frédérique'),  # supported characters
            Disbursement(1000, 'cheque', 'ARİF', 'Błażej'),  # unsupported characters
            Disbursement(1000, 'bank_transfer', ' ', ''),  # unsupported characters
        ])

    parser = argparse.ArgumentParser(description='Creates a sample prisoner credit notices PDF')
    parser.add_argument('path', help='Path to save the PDF file')
    args = parser.parse_args()
    bundle = PrisonerCreditNoticeBundle('HMP Brixton',
                                        generate_samples(),
                                        datetime.date.today() - datetime.timedelta(days=1))
    bundle.render(args.path)


if __name__ == '__main__':
    create_sample()
