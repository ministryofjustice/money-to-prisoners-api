import codecs
import collections
import re

from django.utils.translation import gettext as _

from credit.notices import NoticeBundle, get_asset_path
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
                    'WING': _('Wing'),
                    'LAND': _('Landing'),
                    'CELL': _('Cell'),
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

        self.render_security_box()

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

    def render_security_box(self):
        # top, bottom = 120, 209
        # vertical_gutter, horizontal_gutter = 9.5, 10
        # security_bounds = (
        #     horizontal_gutter,
        #     top + vertical_gutter,
        #     self.page_width - horizontal_gutter,
        #     bottom - vertical_gutter,
        # )
        # security_width = int(security_bounds[2] - security_bounds[0])
        # security_height = int(security_bounds[3] - security_bounds[1])
        # security_lines = []
        # for shift in range(0, security_height, 2):
        #     security_lines.append(
        #         (security_bounds[0], security_bounds[1] + shift,
        #          security_bounds[0] + security_height - shift, security_bounds[3])
        #     )
        # for shift in range(2, security_width, 2):
        #     if shift > security_width - security_height:
        #         security_lines.append(
        #             (security_bounds[0] + shift, security_bounds[1],
        #              security_bounds[2], security_bounds[3] - shift + security_width - security_height)
        #         )
        #     else:
        #         security_lines.append(
        #             (security_bounds[0] + shift, security_bounds[1],
        #              security_bounds[0] + security_height + shift, security_bounds[3])
        #         )
        # security_lines += [
        #     (self.page_width - x1, y1, (self.page_width - x2), y2)
        #     for x1, y1, x2, y2 in security_lines
        # ]
        security_lines = [
            (10, 129.5, 80, 199.5), (10, 131.5, 78, 199.5), (10, 133.5, 76, 199.5), (10, 135.5, 74, 199.5),
            (10, 137.5, 72, 199.5), (10, 139.5, 70, 199.5), (10, 141.5, 68, 199.5), (10, 143.5, 66, 199.5),
            (10, 145.5, 64, 199.5), (10, 147.5, 62, 199.5), (10, 149.5, 60, 199.5), (10, 151.5, 58, 199.5),
            (10, 153.5, 56, 199.5), (10, 155.5, 54, 199.5), (10, 157.5, 52, 199.5), (10, 159.5, 50, 199.5),
            (10, 161.5, 48, 199.5), (10, 163.5, 46, 199.5), (10, 165.5, 44, 199.5), (10, 167.5, 42, 199.5),
            (10, 169.5, 40, 199.5), (10, 171.5, 38, 199.5), (10, 173.5, 36, 199.5), (10, 175.5, 34, 199.5),
            (10, 177.5, 32, 199.5), (10, 179.5, 30, 199.5), (10, 181.5, 28, 199.5), (10, 183.5, 26, 199.5),
            (10, 185.5, 24, 199.5), (10, 187.5, 22, 199.5), (10, 189.5, 20, 199.5), (10, 191.5, 18, 199.5),
            (10, 193.5, 16, 199.5), (10, 195.5, 14, 199.5), (10, 197.5, 12, 199.5), (12, 129.5, 82, 199.5),
            (14, 129.5, 84, 199.5), (16, 129.5, 86, 199.5), (18, 129.5, 88, 199.5), (20, 129.5, 90, 199.5),
            (22, 129.5, 92, 199.5), (24, 129.5, 94, 199.5), (26, 129.5, 96, 199.5), (28, 129.5, 98, 199.5),
            (30, 129.5, 100, 199.5), (32, 129.5, 102, 199.5), (34, 129.5, 104, 199.5), (36, 129.5, 106, 199.5),
            (38, 129.5, 108, 199.5), (40, 129.5, 110, 199.5), (42, 129.5, 112, 199.5), (44, 129.5, 114, 199.5),
            (46, 129.5, 116, 199.5), (48, 129.5, 118, 199.5), (50, 129.5, 120, 199.5), (52, 129.5, 122, 199.5),
            (54, 129.5, 124, 199.5), (56, 129.5, 126, 199.5), (58, 129.5, 128, 199.5), (60, 129.5, 130, 199.5),
            (62, 129.5, 132, 199.5), (64, 129.5, 134, 199.5), (66, 129.5, 136, 199.5), (68, 129.5, 138, 199.5),
            (70, 129.5, 140, 199.5), (72, 129.5, 142, 199.5), (74, 129.5, 144, 199.5), (76, 129.5, 146, 199.5),
            (78, 129.5, 148, 199.5), (80, 129.5, 150, 199.5), (82, 129.5, 152, 199.5), (84, 129.5, 154, 199.5),
            (86, 129.5, 156, 199.5), (88, 129.5, 158, 199.5), (90, 129.5, 160, 199.5), (92, 129.5, 162, 199.5),
            (94, 129.5, 164, 199.5), (96, 129.5, 166, 199.5), (98, 129.5, 168, 199.5), (100, 129.5, 170, 199.5),
            (102, 129.5, 172, 199.5), (104, 129.5, 174, 199.5), (106, 129.5, 176, 199.5), (108, 129.5, 178, 199.5),
            (110, 129.5, 180, 199.5), (112, 129.5, 182, 199.5), (114, 129.5, 184, 199.5), (116, 129.5, 186, 199.5),
            (118, 129.5, 188, 199.5), (120, 129.5, 190, 199.5), (122, 129.5, 192, 199.5), (124, 129.5, 194, 199.5),
            (126, 129.5, 196, 199.5), (128, 129.5, 198, 199.5), (130, 129.5, 200, 199.5), (132, 129.5, 200, 197.5),
            (134, 129.5, 200, 195.5), (136, 129.5, 200, 193.5), (138, 129.5, 200, 191.5), (140, 129.5, 200, 189.5),
            (142, 129.5, 200, 187.5), (144, 129.5, 200, 185.5), (146, 129.5, 200, 183.5), (148, 129.5, 200, 181.5),
            (150, 129.5, 200, 179.5), (152, 129.5, 200, 177.5), (154, 129.5, 200, 175.5), (156, 129.5, 200, 173.5),
            (158, 129.5, 200, 171.5), (160, 129.5, 200, 169.5), (162, 129.5, 200, 167.5), (164, 129.5, 200, 165.5),
            (166, 129.5, 200, 163.5), (168, 129.5, 200, 161.5), (170, 129.5, 200, 159.5), (172, 129.5, 200, 157.5),
            (174, 129.5, 200, 155.5), (176, 129.5, 200, 153.5), (178, 129.5, 200, 151.5), (180, 129.5, 200, 149.5),
            (182, 129.5, 200, 147.5), (184, 129.5, 200, 145.5), (186, 129.5, 200, 143.5), (188, 129.5, 200, 141.5),
            (190, 129.5, 200, 139.5), (192, 129.5, 200, 137.5), (194, 129.5, 200, 135.5), (196, 129.5, 200, 133.5),
            (198, 129.5, 200, 131.5), (200, 129.5, 130, 199.5), (200, 131.5, 132, 199.5), (200, 133.5, 134, 199.5),
            (200, 135.5, 136, 199.5), (200, 137.5, 138, 199.5), (200, 139.5, 140, 199.5), (200, 141.5, 142, 199.5),
            (200, 143.5, 144, 199.5), (200, 145.5, 146, 199.5), (200, 147.5, 148, 199.5), (200, 149.5, 150, 199.5),
            (200, 151.5, 152, 199.5), (200, 153.5, 154, 199.5), (200, 155.5, 156, 199.5), (200, 157.5, 158, 199.5),
            (200, 159.5, 160, 199.5), (200, 161.5, 162, 199.5), (200, 163.5, 164, 199.5), (200, 165.5, 166, 199.5),
            (200, 167.5, 168, 199.5), (200, 169.5, 170, 199.5), (200, 171.5, 172, 199.5), (200, 173.5, 174, 199.5),
            (200, 175.5, 176, 199.5), (200, 177.5, 178, 199.5), (200, 179.5, 180, 199.5), (200, 181.5, 182, 199.5),
            (200, 183.5, 184, 199.5), (200, 185.5, 186, 199.5), (200, 187.5, 188, 199.5), (200, 189.5, 190, 199.5),
            (200, 191.5, 192, 199.5), (200, 193.5, 194, 199.5), (200, 195.5, 196, 199.5), (200, 197.5, 198, 199.5),
            (198, 129.5, 128, 199.5), (196, 129.5, 126, 199.5), (194, 129.5, 124, 199.5), (192, 129.5, 122, 199.5),
            (190, 129.5, 120, 199.5), (188, 129.5, 118, 199.5), (186, 129.5, 116, 199.5), (184, 129.5, 114, 199.5),
            (182, 129.5, 112, 199.5), (180, 129.5, 110, 199.5), (178, 129.5, 108, 199.5), (176, 129.5, 106, 199.5),
            (174, 129.5, 104, 199.5), (172, 129.5, 102, 199.5), (170, 129.5, 100, 199.5), (168, 129.5, 98, 199.5),
            (166, 129.5, 96, 199.5), (164, 129.5, 94, 199.5), (162, 129.5, 92, 199.5), (160, 129.5, 90, 199.5),
            (158, 129.5, 88, 199.5), (156, 129.5, 86, 199.5), (154, 129.5, 84, 199.5), (152, 129.5, 82, 199.5),
            (150, 129.5, 80, 199.5), (148, 129.5, 78, 199.5), (146, 129.5, 76, 199.5), (144, 129.5, 74, 199.5),
            (142, 129.5, 72, 199.5), (140, 129.5, 70, 199.5), (138, 129.5, 68, 199.5), (136, 129.5, 66, 199.5),
            (134, 129.5, 64, 199.5), (132, 129.5, 62, 199.5), (130, 129.5, 60, 199.5), (128, 129.5, 58, 199.5),
            (126, 129.5, 56, 199.5), (124, 129.5, 54, 199.5), (122, 129.5, 52, 199.5), (120, 129.5, 50, 199.5),
            (118, 129.5, 48, 199.5), (116, 129.5, 46, 199.5), (114, 129.5, 44, 199.5), (112, 129.5, 42, 199.5),
            (110, 129.5, 40, 199.5), (108, 129.5, 38, 199.5), (106, 129.5, 36, 199.5), (104, 129.5, 34, 199.5),
            (102, 129.5, 32, 199.5), (100, 129.5, 30, 199.5), (98, 129.5, 28, 199.5), (96, 129.5, 26, 199.5),
            (94, 129.5, 24, 199.5), (92, 129.5, 22, 199.5), (90, 129.5, 20, 199.5), (88, 129.5, 18, 199.5),
            (86, 129.5, 16, 199.5), (84, 129.5, 14, 199.5), (82, 129.5, 12, 199.5), (80, 129.5, 10, 199.5),
            (78, 129.5, 10, 197.5), (76, 129.5, 10, 195.5), (74, 129.5, 10, 193.5), (72, 129.5, 10, 191.5),
            (70, 129.5, 10, 189.5), (68, 129.5, 10, 187.5), (66, 129.5, 10, 185.5), (64, 129.5, 10, 183.5),
            (62, 129.5, 10, 181.5), (60, 129.5, 10, 179.5), (58, 129.5, 10, 177.5), (56, 129.5, 10, 175.5),
            (54, 129.5, 10, 173.5), (52, 129.5, 10, 171.5), (50, 129.5, 10, 169.5), (48, 129.5, 10, 167.5),
            (46, 129.5, 10, 165.5), (44, 129.5, 10, 163.5), (42, 129.5, 10, 161.5), (40, 129.5, 10, 159.5),
            (38, 129.5, 10, 157.5), (36, 129.5, 10, 155.5), (34, 129.5, 10, 153.5), (32, 129.5, 10, 151.5),
            (30, 129.5, 10, 149.5), (28, 129.5, 10, 147.5), (26, 129.5, 10, 145.5), (24, 129.5, 10, 143.5),
            (22, 129.5, 10, 141.5), (20, 129.5, 10, 139.5), (18, 129.5, 10, 137.5), (16, 129.5, 10, 135.5),
            (14, 129.5, 10, 133.5), (12, 129.5, 10, 131.5),
        ]
        self.draw_lines(security_lines)


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
                {'type': 'WING', 'value': 'A'},
                {'type': 'LAND', 'value': '2'},
                {'type': 'CELL', 'value': '002'}
            ],
        }, [], [])
        yield ('JILLY HALL', 'A1401AE', {
            'description': 'LEI-B-2-002',
            'levels': [
                {'type': 'WING', 'value': 'B'},
                {'type': 'LAND', 'value': '2'},
                {'type': 'CELL', 'value': '002'}
            ],
        }, [
            Credit(2000, 'JORDAN MARSH'),
            Credit(3000, 'MRS J MARSH'),
        ], [])
        yield ('JILLY HALL', 'A1401AE', {
            'description': 'LEI-C-2-002',
            'levels': [
                {'type': 'WING', 'value': 'C'},
                {'type': 'LAND', 'value': '2'},
                {'type': 'CELL', 'value': '002'}
            ],
        }, [], [
            Disbursement(10000, 'cheque', 'thomas', 'raymond'),
        ])
        yield ('JAMES HALLS', 'A1409AE', {
            'description': 'LEI-A-2-002',
            'levels': [
                {'type': 'WING', 'value': 'A'},
                {'type': 'LAND', 'value': '2'},
                {'type': 'CELL', 'value': '002'}
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
                {'type': 'WING', 'value': 'B'},
                {'type': 'LAND', 'value': '1'},
                {'type': 'CELL', 'value': '002'}
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
