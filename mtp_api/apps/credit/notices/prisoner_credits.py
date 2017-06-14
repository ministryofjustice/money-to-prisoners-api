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
        top = 235
        left = 40
        row_height = 10
        col_gap = 2
        col_stride = 106
        amount_width = 22
        sender_width = 62
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
            else:
                self.change_font('NTA-Bold', 12)
            self.draw_text(x, y, amount, align='R')

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
        self.draw_image(get_asset_path('logo.png'), x=94.558, y=62, w=20.884, h=17.321)
        self.change_font('NTA-Light', 12)
        self.draw_text(105, 85, _('Send money to someone in prison'), align='C')

        self.change_font('NTA-Light', 8)
        fold_text = _('Confidential. Please fold & staple')
        fold_line_width = (self.page_width - self.text_width(fold_text) - 3) / 2
        half_page_height = self.page_height / 2
        self.draw_text(105, half_page_height, fold_text, align='C')
        self.draw_line(0, half_page_height, fold_line_width, half_page_height)
        self.draw_line(self.page_width - fold_line_width, half_page_height, self.page_width, half_page_height)

        self.change_font('NTA-Light', 12)
        self.draw_text(19, 208, _('You have been sent money online.'))
        self.draw_text(19, 214, _('You may not have all this money to spend in canteen.'))

        staple = get_asset_path('staple.png')
        self.draw_image(staple, x=100.74, y=8, w=8.52, h=1.738)
        self.draw_image(staple, x=100.74, y=287.262, w=8.52, h=1.738)

    def render_header(self, name, number):
        self.change_font('NTA-Bold', 19)
        self.draw_text(19, 177, name)

        self.change_font('NTA-Light', 16)
        self.draw_text(19, 185, number)

        self.change_font('NTA-Light', 12)
        self.draw_text(191, 177, self.human_date, align='R')
