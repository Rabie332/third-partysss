import datetime
import logging
from collections import defaultdict

from odoo import fields, models
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class HolidaysType(models.Model):
    _inherit = "hr.leave.type"

    maximum_days = fields.Integer(string="Maximum Days")
    for_gender = fields.Selection(
        [("both", "Both"), ("male", "Male"), ("female", "Female")],
        default="both",
        string="For",
    )
    attachment_required = fields.Boolean(string="attachments is necessary")
    is_start_specific_date = fields.Boolean(
        string="The number of days starting from specific date"
    )
    is_before_specific_date = fields.Boolean(string="Before specified date")
    days_before_specific_date = fields.Integer(
        string="Number Days before specified date"
    )
    count_weekend = fields.Boolean(string="Count Weekend")
    count_public_holidays = fields.Boolean(string="Count public holidays")
    holidays_including_weekend_public = fields.Boolean(
        string="Not to allow submission on weekends, official holidays and holidays"
    )
    depassed_trial_period = fields.Boolean(string="Depassed Trial Period")
    active = fields.Boolean(default=True)
    availability = fields.Integer("Aavailability of last stock", default=90)
    without_current_sold = fields.Boolean(string="Can take without current sold")

    def _search_max_leaves(self, operator, value):
        value = float(value)
        employee_id = self._get_contextual_employee_id()
        leaves = defaultdict(int)

        if employee_id:
            allocations = self.env["hr.leave.allocation"].search(
                [("employee_id", "=", employee_id), ("state", "=", "done")]
            )
            for allocation in allocations:
                leaves[allocation.holiday_status_id.id] += allocation.number_of_days
        valid_leave = []
        for leave in leaves:
            if operator == ">":
                if leaves[leave] > value:
                    valid_leave.append(leave)
            elif operator == "<":
                if leaves[leave] < value:
                    valid_leave.append(leave)
            elif operator == "=":
                if leaves[leave] == value:
                    valid_leave.append(leave)
            elif operator == "!=":
                if leaves[leave] != value:
                    valid_leave.append(leave)

        return [("id", "in", valid_leave)]

    def get_days(self, employee_id):
        # need to use `dict` constructor to create a dict per id
        result = {
            id: dict(
                max_leaves=0,
                leaves_taken=0,
                remaining_leaves=0,
                virtual_remaining_leaves=0,
            )
            for id in self.ids
        }

        requests = self.env["hr.leave"].search(
            [
                ("employee_id", "=", employee_id),
                ("state", "in", ["in_progress", "done"]),
                ("holiday_status_id", "in", self.ids),
            ]
        )

        allocations = self.env["hr.leave.allocation"].search(
            [
                ("employee_id", "=", employee_id),
                ("state", "in", ["in_progress", "done"]),
                ("holiday_status_id", "in", self.ids),
            ]
        )

        for request in requests:
            status_dict = result[request.holiday_status_id.id]
            status_dict["virtual_remaining_leaves"] -= (
                request.number_of_hours_display
                if request.leave_type_request_unit == "hour"
                else request.number_of_days
            )
            if request.state == "done":
                status_dict["leaves_taken"] += (
                    request.number_of_hours_display
                    if request.leave_type_request_unit == "hour"
                    else request.number_of_days
                )
                status_dict["remaining_leaves"] -= (
                    request.number_of_hours_display
                    if request.leave_type_request_unit == "hour"
                    else request.number_of_days
                )

        for allocation in allocations.sudo():
            status_dict = result[allocation.holiday_status_id.id]
            if allocation.state == "done":
                # note: add only validated allocation even for the virtual
                # count; otherwise pending then refused allocation allow
                # the employee to create more leaves than possible
                status_dict["virtual_remaining_leaves"] += (
                    allocation.number_of_hours_display
                    if allocation.type_request_unit == "hour"
                    else allocation.number_of_days
                )
                status_dict["max_leaves"] += (
                    allocation.number_of_hours_display
                    if allocation.type_request_unit == "hour"
                    else allocation.number_of_days
                )
                status_dict["remaining_leaves"] += (
                    allocation.number_of_hours_display
                    if allocation.type_request_unit == "hour"
                    else allocation.number_of_days
                )

        return result

    def _compute_group_days_allocation(self):
        domain = [
            ("holiday_status_id", "in", self.ids),
            ("holiday_type", "!=", "employee"),
            ("state", "=", "done"),
        ]
        domain2 = [
            "|",
            (
                "date_from",
                ">=",
                fields.Datetime.to_string(
                    datetime.datetime.now().replace(
                        month=1, day=1, hour=0, minute=0, second=0, microsecond=0
                    )
                ),
            ),
            ("date_from", "=", False),
        ]
        grouped_res = self.env["hr.leave.allocation"].read_group(
            expression.AND([domain, domain2]),
            ["holiday_status_id", "number_of_days"],
            ["holiday_status_id"],
        )
        grouped_dict = {
            data["holiday_status_id"][0]: data["number_of_days"] for data in grouped_res
        }
        for allocation in self:
            allocation.group_days_allocation = grouped_dict.get(allocation.id, 0)

    def _compute_group_days_leave(self):
        grouped_res = self.env["hr.leave"].read_group(
            [
                ("holiday_status_id", "in", self.ids),
                ("holiday_type", "=", "employee"),
                ("state", "=", "done"),
                (
                    "date_from",
                    ">=",
                    fields.Datetime.to_string(
                        datetime.datetime.now().replace(
                            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
                        )
                    ),
                ),
            ],
            ["holiday_status_id"],
            ["holiday_status_id"],
        )
        grouped_dict = {
            data["holiday_status_id"][0]: data["holiday_status_id_count"]
            for data in grouped_res
        }
        for allocation in self:
            allocation.group_days_leave = grouped_dict.get(allocation.id, 0)

    def get_employees_days(self, employee_ids):
        result = {
            employee_id: {
                leave_type.id: {
                    "max_leaves": 0,
                    "leaves_taken": 0,
                    "remaining_leaves": 0,
                    "virtual_remaining_leaves": 0,
                }
                for leave_type in self
            }
            for employee_id in employee_ids
        }

        requests = self.env["hr.leave"].search(
            [
                ("employee_id", "in", employee_ids),
                ("state", "in", ["done"]),
                ("holiday_status_id", "in", self.ids),
            ]
        )
        allocations = self.env["hr.leave.allocation"].search(
            [
                ("employee_id", "in", employee_ids),
                ("state", "=", "done"),
                ("holiday_status_id", "in", self.ids),
            ]
        )

        for request in requests:
            status_dict = result[request.employee_id.id][request.holiday_status_id.id]
            status_dict["virtual_remaining_leaves"] -= (
                request.number_of_hours_display
                if request.leave_type_request_unit == "hour"
                else request.number_of_days
            )
            if request.state == "done":
                status_dict["leaves_taken"] += (
                    request.number_of_hours_display
                    if request.leave_type_request_unit == "hour"
                    else request.number_of_days
                )
                status_dict["remaining_leaves"] -= (
                    request.number_of_hours_display
                    if request.leave_type_request_unit == "hour"
                    else request.number_of_days
                )

        for allocation in allocations.sudo():
            status_dict = result[allocation.employee_id.id][
                allocation.holiday_status_id.id
            ]
            if allocation.state == "done":
                # note: add only validated allocation even for the virtual
                # count; otherwise pending then refused allocation allow
                # the employee to create more leaves than possible
                status_dict["virtual_remaining_leaves"] += (
                    allocation.number_of_hours_display
                    if allocation.type_request_unit == "hour"
                    else allocation.number_of_days
                )
                status_dict["max_leaves"] += (
                    allocation.number_of_hours_display
                    if allocation.type_request_unit == "hour"
                    else allocation.number_of_days
                )
                status_dict["remaining_leaves"] += (
                    allocation.number_of_hours_display
                    if allocation.type_request_unit == "hour"
                    else allocation.number_of_days
                )
        return result
