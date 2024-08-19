# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, tools


class LeaveReportCalendar(models.Model):
    _inherit = "hr.leave.report.calendar"

    state = fields.Selection(
        selection_add=[("in_progress", "In progress"), ("done", "Done")]
    )

    def init(self):
        tools.drop_view_if_exists(self._cr, "hr_leave_report_calendar")
        self._cr.execute(
            """CREATE OR REPLACE VIEW hr_leave_report_calendar AS
        (SELECT
            row_number() OVER() AS id,
            CONCAT(em.name, ': ', hl.duration_display) AS name,
            hl.date_from AS start_datetime,
            hl.date_to AS stop_datetime,
            hl.employee_id AS employee_id,
            hl.state AS state,
            em.company_id AS company_id,
            CASE
                WHEN hl.holiday_type = 'employee' THEN rr.tz
                ELSE %s
            END AS tz
        FROM hr_leave hl
            LEFT JOIN hr_employee em
                ON em.id = hl.employee_id
            LEFT JOIN resource_resource rr
                ON rr.id = em.resource_id
        WHERE
            hl.state IN ('in_progress', 'done')
        ORDER BY id);
        """,
            [self.env.company.resource_calendar_id.tz or self.env.user.tz or "UTC"],
        )
