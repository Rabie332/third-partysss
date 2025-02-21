# Part of Odoo. See LICENSE file for full copyright and licensing details.

import datetime

from dateutil.relativedelta import relativedelta

from odoo import fields, models


class Department(models.Model):

    _inherit = "hr.department"

    def _compute_leave_count(self):
        Requests = self.env["hr.leave"]
        Allocations = self.env["hr.leave.allocation"]
        today_date = datetime.datetime.utcnow().date()
        today_start = fields.Datetime.to_string(
            today_date
        )  # get the midnight of the current utc day
        today_end = fields.Datetime.to_string(
            today_date + relativedelta(hours=23, minutes=59, seconds=59)
        )

        leave_data = Requests.read_group(
            [("department_id", "in", self.ids), ("state", "=", "in_progress")],
            ["department_id"],
            ["department_id"],
        )
        allocation_data = Allocations.read_group(
            [("department_id", "in", self.ids), ("state", "=", "in_progress")],
            ["department_id"],
            ["department_id"],
        )
        absence_data = Requests.read_group(
            [
                ("department_id", "in", self.ids),
                ("state", "not in", ["cancel", "refuse"]),
                ("date_from", "<=", today_end),
                ("date_to", ">=", today_start),
            ],
            ["department_id"],
            ["department_id"],
        )

        res_leave = {
            data["department_id"][0]: data["department_id_count"] for data in leave_data
        }
        res_allocation = {
            data["department_id"][0]: data["department_id_count"]
            for data in allocation_data
        }
        res_absence = {
            data["department_id"][0]: data["department_id_count"]
            for data in absence_data
        }

        for department in self:
            department.leave_to_approve_count = res_leave.get(department.id, 0)
            department.allocation_to_approve_count = res_allocation.get(
                department.id, 0
            )
            department.absence_of_today = res_absence.get(department.id, 0)
