import datetime

from odoo import fields, models


class HrEmployeeBase(models.AbstractModel):
    _inherit = "hr.employee.base"

    current_leave_state = fields.Selection(
        selection_add=[("in_progress", "In progress"), ("done", "Done")], tracking=True
    )

    def _get_remaining_leaves(self):
        """Helper to compute the remaining leaves for the current employees
        :returns dict where the key is the employee id, and the value is the remain leaves
        """
        # Fixme: Check Sql request state become "done".
        self._cr.execute(
            """
            SELECT
                sum(h.number_of_days) AS days,
                h.employee_id
            FROM
                (
                    SELECT holiday_status_id, number_of_days,
                        state, employee_id
                    FROM hr_leave_allocation
                    UNION ALL
                    SELECT holiday_status_id, (number_of_days * -1) as number_of_days,
                        state, employee_id
                    FROM hr_leave
                ) h
                join hr_leave_type s ON (s.id=h.holiday_status_id)
            WHERE
                s.active = true AND h.state='done' AND
                (s.allocation_type='fixed' OR s.allocation_type='fixed_allocation') AND
                h.employee_id in %s
            GROUP BY h.employee_id""",
            (tuple(self.ids),),
        )
        return {row["employee_id"]: row["days"] for row in self._cr.dictfetchall()}

    def _compute_allocation_count(self):
        for employee in self:
            # Fixme: Check state become "done".
            allocations = self.env["hr.leave.allocation"].search(
                [
                    ("employee_id", "=", employee.id),
                    ("holiday_status_id.active", "=", True),
                    ("state", "=", "done"),
                    "|",
                    ("date_to", "=", False),
                    ("date_to", ">=", datetime.date.today()),
                ]
            )
            employee.allocation_count = sum(allocations.mapped("number_of_days"))
            employee.allocation_display = "%g" % employee.allocation_count

    def _get_date_start_work(self):
        return self.date_direct_action if self.date_direct_action else self.create_date
