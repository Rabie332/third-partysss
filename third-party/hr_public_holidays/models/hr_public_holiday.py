import math
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

HOURS_PER_DAY = 7


class HrPublicHoliday(models.Model):
    _name = "hr.public.holiday"
    _inherit = ["request"]
    _description = "Public Holiday"

    name = fields.Char(
        string="Eid / Holiday",
        required=1,
        readonly=1,
        states={"draft": [("readonly", 0)]},
    )
    date_from = fields.Date(
        string="From",
        required=1,
        readonly=1,
        states={"draft": [("readonly", 0)]},
        index=1,
    )
    date_to = fields.Date(
        string=" To",
        required=1,
        readonly=1,
        states={"draft": [("readonly", 0)]},
        index=1,
    )
    number_of_days = fields.Float(
        string="Duration by day",
        required=1,
        readonly=1,
        states={"draft": [("readonly", 0)]},
    )
    absent_multip_percent = fields.Float(
        string="Double the day of absence by (%)",
        default=200,
        readonly=1,
        states={"draft": [("readonly", 0)]},
    )
    days_after_eid_start = fields.Integer(
        string="The period from the end of the holiday (days)",
        default=3,
        readonly=1,
        states={"draft": [("readonly", 0)]},
    )

    @api.constrains("date_from", "date_to")
    def _check_date(self):
        for holiday in self.search([]):
            domain = [
                ("date_from", "<=", holiday.date_to),
                ("date_to", ">=", holiday.date_from),
                ("id", "!=", holiday.id),
            ]
            nbr_holidays = self.search_count(domain)
            if nbr_holidays:
                raise ValidationError(_("Dates overlap with a previous holiday"))

    @api.constrains("date_from", "date_to")
    def _check_dates_period(self):
        self.ensure_one()
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError(
                _("The date of 'from' should be smaller than the date of 'to'")
            )

    @api.onchange("date_from")
    def _onchange_date_from(self):
        # No date_to set so far: automatically compute one 8 hours later
        if self.date_from and not self.date_to:
            date_to_with_delta = self.date_from + timedelta(hours=HOURS_PER_DAY)
            self.date_to = str(date_to_with_delta)

        # Compute and update the number of days
        if (self.date_to and self.date_from) and (self.date_from <= self.date_to):
            self.number_of_days = self._get_number_of_days(self.date_from, self.date_to)
        else:
            self.number_of_days = 0

    @api.onchange("date_to")
    def _onchange_date_to(self):
        # Update the number_of_days
        # Compute and update the number of days
        if (self.date_to and self.date_from) and (self.date_from <= self.date_to):
            self.number_of_days = self._get_number_of_days(self.date_from, self.date_to)
        else:
            self.number_of_days = 0

    def _get_number_of_days(self, date_from, date_to):
        """Return a float equals to the timedelta between two dates given as string."""
        time_delta = date_to - date_from
        return math.ceil(time_delta.days + float(time_delta.seconds) / 86400) + 1

    def check_public_holiday_day(self, date):
        """Check if date is a public holiday.

        :param date:
        :return: True or False
        """
        holidays = self.search(
            [("state", "=", "done"), ("date_from", "<=", date), ("date_to", ">=", date)]
        )
        return bool(holidays)
