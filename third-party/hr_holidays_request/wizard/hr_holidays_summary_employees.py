from odoo import fields, models


class HolidaysSummaryEmployee(models.TransientModel):
    _inherit = "hr.holidays.summary.employee"

    holiday_type = fields.Selection(
        [
            ("Approved", "Approved"),
            ("Confirmed", "In progress of Confirmation"),
            ("both", "Both Approved and In progress of Confirmation"),
        ],
        string="Select Time Off Type",
        required=True,
        default="Approved",
    )
