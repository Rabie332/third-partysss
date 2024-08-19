from odoo.tests import common

from odoo.addons.mail.tests.common import mail_new_test_user


class TestHrPublicHolidaysBase(common.TransactionCase):
    def setUp(self):
        super(TestHrPublicHolidaysBase, self).setUp()

        # Create user that has group base.group_user
        self.user = mail_new_test_user(self.env, login="user", groups="base.group_user")

        # Create public holiday manager that has group base.group_user
        self.user_public_holidays_manager = mail_new_test_user(
            self.env, login="holidays_manager", groups="base.group_user"
        )

        self.employee = self.env["hr.employee"].create(
            {
                "name": "Employee",
                "user_id": self.user.id,
                "job_id": self.env.ref("hr.job_consultant").id,
            }
        )

        # Get stage send
        self.stage_send = self.env.ref(
            "hr_public_holidays.hr_public_holiday_stage_send"
        )

        # stage validate will be approved by user_public_holidays_manager
        self.validate = self.env.ref(
            "hr_public_holidays.hr_public_holiday_stage_validate"
        )
        self.validate.write(
            {
                "assign_type": "user",
                "default_user_id": self.user_public_holidays_manager,
            }
        )

        # stage done will be send feedback to employee
        self.hr_public_holidays_stage_done = self.env.ref(
            "hr_public_holidays.hr_public_holiday_stage_done"
        )
        self.hr_public_holidays_stage_done.write(
            {"assign_type": "user", "default_user_id": self.employee.user_id}
        )

        # stage refuse will be send feedback to employee
        self.hr_public_holidays_stage_refused = self.env.ref(
            "hr_public_holidays.hr_public_holiday_stage_refused"
        )
        self.hr_public_holidays_stage_refused.write(
            {"assign_type": "user", "default_user_id": self.employee.user_id}
        )
