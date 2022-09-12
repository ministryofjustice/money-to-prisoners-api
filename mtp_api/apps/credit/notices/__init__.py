import pathlib
import re

from django.conf import settings
from django.utils.translation import gettext as _
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

assets_path = pathlib.Path(__file__).parent.absolute()


def get_asset_path(path):
    return str(assets_path / path)


registerFont(TTFont('NTA-Light', get_asset_path('gds-light.ttf')))
registerFont(TTFont('NTA-Bold', get_asset_path('gds-bold.ttf')))


class NoticeBundle:
    """
    Generic tool for creating PDF bundles
    """
    page_width = 210
    page_height = 297

    def __init__(self):
        self.canvas = None  # type: Canvas
        self.text_y_adjust = 0

    @property
    def author(self):
        return _('His Majesty’s Prison and Probation Service')

    @property
    def creator(self):
        return 'MTP-%s/%s/%s' % (settings.APP, settings.ENVIRONMENT, settings.APP_GIT_COMMIT)

    @property
    def title(self):
        raise NotImplementedError

    @property
    def subject(self):
        return _('Prisoner money')

    def render(self, path):
        canvas = Canvas(path, pagesize=A4, pageCompression=1)
        canvas.setTitle(self.title)
        canvas.setSubject(self.subject)
        canvas.setAuthor(self.author)
        canvas.setCreator(self.creator)
        canvas._doc.info.producer = self.creator
        self.canvas = canvas
        self.render_pages()
        self.canvas.save()

    def render_pages(self):
        raise NotImplementedError

    def change_font(self, font, size):
        self.text_y_adjust = size / 4
        self.canvas.setFont(font, size)

    def text_width(self, text):
        return self.canvas.stringWidth(text) / mm

    def truncate_text_to_width(self, width, text, ellipsis='…'):
        text_width = self.text_width(text)
        if text_width <= width:
            return text
        boundaries = []

        def record_boundary(match):
            boundaries.append(match.span()[0])
            return ' '

        re.sub(r'\W', record_boundary, text)
        if boundaries:
            truncated_text = text
            while boundaries and text_width > width:
                truncated_text = text[:boundaries.pop()] + ellipsis
                text_width = self.text_width(truncated_text)
        else:
            truncated_text = text + ellipsis
            while text_width > width:
                truncated_text = truncated_text[:-2] + ellipsis
                text_width = self.text_width(truncated_text)
        return truncated_text

    def draw_text(self, x, y, text, align='L'):
        x *= mm
        if align == 'R':
            x -= self.canvas.stringWidth(text)
        elif align == 'C':
            x -= self.canvas.stringWidth(text) / 2
        self.canvas.drawString(x, (self.page_height - y) * mm - self.text_y_adjust, text)

    def draw_image(self, path, x, y, w, h):
        self.canvas.drawImage(path, x * mm, (self.page_height - y - h) * mm, width=w * mm, height=h * mm)

    def draw_line(self, x1, y1, x2, y2):
        self.canvas.line(x1 * mm, (self.page_height - y1) * mm, x2 * mm, (self.page_height - y2) * mm)

    def draw_lines(self, lines):
        self.canvas.lines(
            (x1 * mm, (self.page_height - y1) * mm, x2 * mm, (self.page_height - y2) * mm)
            for x1, y1, x2, y2 in lines
        )

    def draw_rect(self, x, y, width, height, **kwargs):
        self.canvas.rect(x * mm, (self.page_height - y - height) * mm, width, height * mm, **kwargs)

    def draw_circle(self, x, y, radius, **kwargs):
        self.canvas.circle(x * mm, (self.page_height - y) * mm, radius * mm, **kwargs)
