import re

from django.utils.translation import gettext as _

from credit.notices import NoticeBundle, get_asset_path
from transaction.utils import format_amount

re_invalid_name = re.compile(r'(\d{6})')
re_whitespace = re.compile(r'\s+')


def format_sender(sender):
    if not sender or re_invalid_name.search(sender):
        # empty or looks like card number
        return _('unknown sender')
    if any(ord(c) > 382 for c in sender):
        # some characters cannot be printed
        return _('unknown sender')
    return re_whitespace.sub(' ', sender.strip()).upper()


class PrisonerCreditNoticeBundle(NoticeBundle):
    """
    Creates a bundle of notices to prisoners receiving credits
    """

    def __init__(self, prison, prisoners, date):
        """
        :param prison: only used in PDF title
        :param prisoners: iterable of (prisoner_name: str, prisoner_number: str, credits: typing.Sequence[Credit])
        :param date: date credits were credited
        """
        super().__init__()
        self.prison = prison
        self.prisoners = prisoners
        self.human_date = date.strftime('%d %b %Y').lstrip('0')

    @property
    def title(self):
        return _('Money credited to prisoners on %(date)s at %(prison)s') % {
            'date': self.human_date,
            'prison': self.prison,
        }

    def render_pages(self):
        for prisoner in self.prisoners:
            self.render_prisoner_pages(*prisoner)

    def render_prisoner_pages(self, name, number, credits_list):
        for page in range(0, len(credits_list), 10):
            self.render_base_template()
            self.render_header(name, number)
            self.render_prisoner_page(credits_list[page:page + 10])
            self.canvas.showPage()

    def render_prisoner_page(self, credits_list):
        top = 237
        left = 30
        row_height = 10
        col_gap = 2
        col_stride = 106
        amount_width = 22
        sender_width = 62 if len(credits_list) > 5 else 146
        line_height = 5
        for index, credit in enumerate(credits_list):
            if index > 4:
                x = left + col_stride
                y = top + (index - 5) * row_height
            else:
                x = left
                y = top + index * row_height

            amount = format_amount(credit.amount, trim_empty_pence=False)
            if self.text_width(amount) > amount_width:
                self.change_font('NTA-Bold', 10)
                amount_y_adjust = 0.2
            else:
                self.change_font('NTA-Bold', 12)
                amount_y_adjust = 0
            self.draw_text(x, y + amount_y_adjust, amount, align='R')

            sender = _('from %s') % format_sender(credit.sender_name)
            self.change_font('NTA-Light', 12)
            if self.text_width(sender) > sender_width:
                sender = sender.split()
                sender_rows = []
                sender_row = []
                while True:
                    sender_row.append(sender.pop(0))
                    if self.text_width(' '.join(sender_row)) > sender_width:
                        if len(sender_row) == 1:
                            sender_rows.append(sender_row[0])
                        else:
                            sender_rows.append(' '.join(sender_row[:-1]))
                            sender.insert(0, sender_row[-1])
                        sender_row = []
                    if not sender:
                        break
                if sender_row:
                    sender_rows.append(' '.join(sender_row))
            else:
                sender_rows = [sender]
            if len(sender_rows) > 2:
                sender_rows = sender_rows[:2]
                sender_rows[-1] += '…'
            for row, sender_row in enumerate(sender_rows):
                self.draw_text(x + col_gap, y + row * line_height, sender_row)

    def render_base_template(self):
        self.draw_image(get_asset_path('logo.png'), x=94.558, y=57, w=20.884, h=17.321)
        self.change_font('NTA-Light', 12)
        self.draw_text(105, 80, _('Send money to someone in prison'), align='C')

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

        self.change_font('NTA-Light', 12)
        message = _('You’ve been sent money online.') + ' ' + _('It’s gone into your private cash account.')
        self.draw_text(110, 225, message, align='C')

        staple = get_asset_path('staple.png')
        self.canvas.setFillGray(1)
        self.canvas.saveState()
        self.canvas.scale(-1, 1)
        self.draw_rect(-11, 160.3, 4.8, 11.4, stroke=0, fill=1)
        self.draw_image(staple, x=-10, y=166-4.2, w=1.8, h=8.4)
        self.canvas.restoreState()
        self.draw_rect(199, 160.3, 4.8, 11.4, stroke=0, fill=1)
        self.draw_image(staple, x=200, y=166-4.2, w=1.8, h=8.4)
        self.canvas.setFillGray(0)

    def render_security_box(self):
        # security_bounds = 10, 122 + 15, self.page_width - 10, 210 - 15
        # security_width = security_bounds[2] - security_bounds[0]
        # security_height = security_bounds[3] - security_bounds[1]
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
            (10, 137, 68, 195), (10, 139, 66, 195), (10, 141, 64, 195), (10, 143, 62, 195), (10, 145, 60, 195),
            (10, 147, 58, 195), (10, 149, 56, 195), (10, 151, 54, 195), (10, 153, 52, 195), (10, 155, 50, 195),
            (10, 157, 48, 195), (10, 159, 46, 195), (10, 161, 44, 195), (10, 163, 42, 195), (10, 165, 40, 195),
            (10, 167, 38, 195), (10, 169, 36, 195), (10, 171, 34, 195), (10, 173, 32, 195), (10, 175, 30, 195),
            (10, 177, 28, 195), (10, 179, 26, 195), (10, 181, 24, 195), (10, 183, 22, 195), (10, 185, 20, 195),
            (10, 187, 18, 195), (10, 189, 16, 195), (10, 191, 14, 195), (10, 193, 12, 195), (12, 137, 70, 195),
            (14, 137, 72, 195), (16, 137, 74, 195), (18, 137, 76, 195), (20, 137, 78, 195), (22, 137, 80, 195),
            (24, 137, 82, 195), (26, 137, 84, 195), (28, 137, 86, 195), (30, 137, 88, 195), (32, 137, 90, 195),
            (34, 137, 92, 195), (36, 137, 94, 195), (38, 137, 96, 195), (40, 137, 98, 195), (42, 137, 100, 195),
            (44, 137, 102, 195), (46, 137, 104, 195), (48, 137, 106, 195), (50, 137, 108, 195), (52, 137, 110, 195),
            (54, 137, 112, 195), (56, 137, 114, 195), (58, 137, 116, 195), (60, 137, 118, 195), (62, 137, 120, 195),
            (64, 137, 122, 195), (66, 137, 124, 195), (68, 137, 126, 195), (70, 137, 128, 195), (72, 137, 130, 195),
            (74, 137, 132, 195), (76, 137, 134, 195), (78, 137, 136, 195), (80, 137, 138, 195), (82, 137, 140, 195),
            (84, 137, 142, 195), (86, 137, 144, 195), (88, 137, 146, 195), (90, 137, 148, 195), (92, 137, 150, 195),
            (94, 137, 152, 195), (96, 137, 154, 195), (98, 137, 156, 195), (100, 137, 158, 195), (102, 137, 160, 195),
            (104, 137, 162, 195), (106, 137, 164, 195), (108, 137, 166, 195), (110, 137, 168, 195),
            (112, 137, 170, 195), (114, 137, 172, 195), (116, 137, 174, 195), (118, 137, 176, 195),
            (120, 137, 178, 195), (122, 137, 180, 195), (124, 137, 182, 195), (126, 137, 184, 195),
            (128, 137, 186, 195), (130, 137, 188, 195), (132, 137, 190, 195), (134, 137, 192, 195),
            (136, 137, 194, 195), (138, 137, 196, 195), (140, 137, 198, 195), (142, 137, 200, 195),
            (144, 137, 200, 193), (146, 137, 200, 191), (148, 137, 200, 189), (150, 137, 200, 187),
            (152, 137, 200, 185), (154, 137, 200, 183), (156, 137, 200, 181), (158, 137, 200, 179),
            (160, 137, 200, 177), (162, 137, 200, 175), (164, 137, 200, 173), (166, 137, 200, 171),
            (168, 137, 200, 169), (170, 137, 200, 167), (172, 137, 200, 165), (174, 137, 200, 163),
            (176, 137, 200, 161), (178, 137, 200, 159), (180, 137, 200, 157), (182, 137, 200, 155),
            (184, 137, 200, 153), (186, 137, 200, 151), (188, 137, 200, 149), (190, 137, 200, 147),
            (192, 137, 200, 145), (194, 137, 200, 143), (196, 137, 200, 141), (198, 137, 200, 139),
            (200, 137, 142, 195), (200, 139, 144, 195), (200, 141, 146, 195), (200, 143, 148, 195),
            (200, 145, 150, 195), (200, 147, 152, 195), (200, 149, 154, 195), (200, 151, 156, 195),
            (200, 153, 158, 195), (200, 155, 160, 195), (200, 157, 162, 195), (200, 159, 164, 195),
            (200, 161, 166, 195), (200, 163, 168, 195), (200, 165, 170, 195), (200, 167, 172, 195),
            (200, 169, 174, 195), (200, 171, 176, 195), (200, 173, 178, 195), (200, 175, 180, 195),
            (200, 177, 182, 195), (200, 179, 184, 195), (200, 181, 186, 195), (200, 183, 188, 195),
            (200, 185, 190, 195), (200, 187, 192, 195), (200, 189, 194, 195), (200, 191, 196, 195),
            (200, 193, 198, 195), (198, 137, 140, 195), (196, 137, 138, 195), (194, 137, 136, 195),
            (192, 137, 134, 195), (190, 137, 132, 195), (188, 137, 130, 195), (186, 137, 128, 195),
            (184, 137, 126, 195), (182, 137, 124, 195), (180, 137, 122, 195), (178, 137, 120, 195),
            (176, 137, 118, 195), (174, 137, 116, 195), (172, 137, 114, 195), (170, 137, 112, 195),
            (168, 137, 110, 195), (166, 137, 108, 195), (164, 137, 106, 195), (162, 137, 104, 195),
            (160, 137, 102, 195), (158, 137, 100, 195), (156, 137, 98, 195), (154, 137, 96, 195), (152, 137, 94, 195),
            (150, 137, 92, 195), (148, 137, 90, 195), (146, 137, 88, 195), (144, 137, 86, 195), (142, 137, 84, 195),
            (140, 137, 82, 195), (138, 137, 80, 195), (136, 137, 78, 195), (134, 137, 76, 195), (132, 137, 74, 195),
            (130, 137, 72, 195), (128, 137, 70, 195), (126, 137, 68, 195), (124, 137, 66, 195), (122, 137, 64, 195),
            (120, 137, 62, 195), (118, 137, 60, 195), (116, 137, 58, 195), (114, 137, 56, 195), (112, 137, 54, 195),
            (110, 137, 52, 195), (108, 137, 50, 195), (106, 137, 48, 195), (104, 137, 46, 195), (102, 137, 44, 195),
            (100, 137, 42, 195), (98, 137, 40, 195), (96, 137, 38, 195), (94, 137, 36, 195), (92, 137, 34, 195),
            (90, 137, 32, 195), (88, 137, 30, 195), (86, 137, 28, 195), (84, 137, 26, 195), (82, 137, 24, 195),
            (80, 137, 22, 195), (78, 137, 20, 195), (76, 137, 18, 195), (74, 137, 16, 195), (72, 137, 14, 195),
            (70, 137, 12, 195), (68, 137, 10, 195), (66, 137, 10, 193), (64, 137, 10, 191), (62, 137, 10, 189),
            (60, 137, 10, 187), (58, 137, 10, 185), (56, 137, 10, 183), (54, 137, 10, 181), (52, 137, 10, 179),
            (50, 137, 10, 177), (48, 137, 10, 175), (46, 137, 10, 173), (44, 137, 10, 171), (42, 137, 10, 169),
            (40, 137, 10, 167), (38, 137, 10, 165), (36, 137, 10, 163), (34, 137, 10, 161), (32, 137, 10, 159),
            (30, 137, 10, 157), (28, 137, 10, 155), (26, 137, 10, 153), (24, 137, 10, 151), (22, 137, 10, 149),
            (20, 137, 10, 147), (18, 137, 10, 145), (16, 137, 10, 143), (14, 137, 10, 141), (12, 137, 10, 139),
        ]
        self.draw_lines(security_lines)

    def render_header(self, name, number):
        baseline = 0.8
        self.change_font('NTA-Bold', 19)
        if self.text_width(name) > 110:
            self.change_font('NTA-Bold', 17)
            baseline = 0.3
        self.draw_text(19, 17, name)

        self.change_font('NTA-Light', 16)
        self.draw_text(19, 25, number)

        self.change_font('NTA-Light', 12)
        self.draw_text(191, 17 + baseline, _('Received on %(date)s') % {'date': self.human_date}, align='R')


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

        yield ('JAMES HALLS', 'A1409AE', [
            Credit(3500, 'JORDAN MARSH'),
            Credit(4000, 'BRETT WILKINS'),
            Credit(2036000, 'SOMEBODY WITH A SIMULATED LONG NAME-THAT-TRUNCATES'),
            Credit(10000, 'JORDAN MARSH'),
            Credit(1000, 'RICHARDSON JUSTIN'),
            Credit(10000, 'POWELL JADE'),
            Credit(1000, 'PAIGE BARTON'),
            Credit(5, 'X GREEN'),
            Credit(5000, 'GARRY CLARK GARRY CLAR'),
            Credit(5000, 'SIMPSON R'),
            Credit(5001, 'Gordon Ian'),
        ])
        yield ('RICKY-LONG LONG-LONG-SURNAME-RIPPIN', 'A1234AA', [
            Credit(2036000, 'SOMEBODY WITH A SIMULATED LONG NAME-THAT-TRUNCATES'),
            Credit(3500, 'AMÉLIE POULAIN'),
            Credit(100000, 'علاء الدين'),
            Credit(1000, 'ІГОР ИГОРЬ'),
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
