from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields, models


class HrHolidaySummaryReport(models.AbstractModel):
    _inherit = "report.hr_holidays.report_holidayssummary"

    def _get_leaves_summary(self, start_date, empid, holiday_type):
        res = []
        count = 0
        start_date = fields.Date.from_string(start_date)
        end_date = start_date + relativedelta(days=59)
        for index in range(0, 60):
            current = start_date + timedelta(index)
            res.append({"day": current.day, "color": ""})
            if self._date_is_day_off(current):
                res[index]["color"] = "#ababab"
        # count and get leave summary details.
        holiday_type = (
            ["in_progress", "done"]
            if holiday_type == "both"
            else ["in_progress"]
            if holiday_type == "Confirmed"
            else ["done"]
        )
        holidays = self.env["hr.leave"].search(
            [
                ("employee_id", "=", empid),
                ("state", "in", holiday_type),
                ("date_from", "<=", str(end_date)),
                ("date_to", ">=", str(start_date)),
            ]
        )
        for holiday in holidays:
            # Convert date to user timezone, otherwise
            # the report will not be consistent with the
            # value displayed in the interface.
            date_from = fields.Datetime.from_string(holiday.date_from)
            date_from = fields.Datetime.context_timestamp(holiday, date_from).date()
            date_to = fields.Datetime.from_string(holiday.date_to)
            date_to = fields.Datetime.context_timestamp(holiday, date_to).date()
            for _index in range(0, ((date_to - date_from).days + 1)):
                if date_from >= start_date and date_from <= end_date:
                    res[(date_from - start_date).days][
                        "color"
                    ] = holiday.holiday_status_id.color_name
                date_from += timedelta(1)
            count += holiday.number_of_days
        self.sum = count
        return res
