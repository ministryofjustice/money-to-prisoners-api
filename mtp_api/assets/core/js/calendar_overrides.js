/*
 * Overrides this function to reverse the x-positioning rules such that the
 * calendar box will appear on the left on a rtl display. This is due to its
 * positioning in the right hand sidebar on the filter list.
 */
DateTimeShortcuts['openCalendar'] = function(num) {
        var cal_box = document.getElementById(DateTimeShortcuts.calendarDivName1+num);
        var cal_link = document.getElementById(DateTimeShortcuts.calendarLinkName+num);
        var inp = DateTimeShortcuts.calendarInputs[num];

        // Determine if the current value in the input has a valid date.
        // If so, draw the calendar with that date's year and month.
        if (inp.value) {
            var format = get_format('DATE_INPUT_FORMATS')[0];
            var selected = inp.value.strptime(format);
            var year = selected.getFullYear();
            var month = selected.getMonth() + 1;
            var re = /\d{4}/;
            if (re.test(year.toString()) && month >= 1 && month <= 12) {
                DateTimeShortcuts.calendars[num].drawDate(month, year, selected);
            }
        }

        // Recalculate the clockbox position
        // is it left-to-right or right-to-left layout ?
        if (getStyle(document.body,'direction')!='rtl') {
            cal_box.style.left = findPosX(cal_link) - 180 + 'px';
        }
        else {
            // since style's width is in em, it'd be tough to calculate
            // px value of it. let's use an estimated px for now
            // TODO: IE returns wrong value for findPosX when in rtl mode
            //       (it returns as it was left aligned), needs to be fixed.
            cal_box.style.left = findPosX(cal_link) +17 + 'px';
        }
        cal_box.style.top = Math.max(0, findPosY(cal_link) - 75) + 'px';

        cal_box.style.display = 'block';
        addEvent(document, 'click', DateTimeShortcuts.dismissCalendarFunc[num]);
    };

/* Override date formats to put ISO format first (avoid overriding language settings) */
django.formats['DATE_INPUT_FORMATS'] = ['%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y'];
