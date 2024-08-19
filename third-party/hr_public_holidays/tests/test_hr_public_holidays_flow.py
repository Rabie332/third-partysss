from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import Form
from odoo.tools import mute_logger

from .common import TestHrPublicHolidaysBase


class TestHrPublicHolidaysFlow(TestHrPublicHolidaysBase):
    @mute_logger("odoo.addons.base.models.ir_model", "odoo.models")
    def test_hr_public_holidays_request_flow(self):

        # user requests a public holidays
        public_holiday_object = self.env["hr.public.holiday"].with_user(self.user)
        public_holiday_form = Form(public_holiday_object)
        public_holiday_form.name = "Holiday"
        public_holiday_form.date_from = date(2020, 3, 1)
        public_holiday_form.date_to = date(2020, 3, 3)
        public_holiday_form.stage_id = self.stage_send
        self.public_holiday = public_holiday_form.save()

        # check request has the right stage and state

        self.assertEqual(self.public_holiday.stage_id.name, "Send")
        self.assertEqual(self.public_holiday.state, "draft")

        # Create another public holiday and test constraint
        # _check_date : Dates overlap with a previous holiday

        other_public_holiday_form = Form(public_holiday_object)
        other_public_holiday_form.name = "Other Holiday"
        other_public_holiday_form.date_from = date(2020, 5, 3)
        other_public_holiday_form.date_to = date(2020, 5, 4)
        other_public_holiday_form.stage_id = self.stage_send
        self.other_public_holiday = other_public_holiday_form.save()

        with self.assertRaises(ValidationError):
            self.other_public_holiday.write(
                {"date_from": date(2020, 3, 1), "date_to": date(2020, 3, 2)}
            )

        # test constraint _check_dates_period: date_from should be smaller than date_to

        other_public_holiday_form.date_from = date(2020, 4, 4)
        other_public_holiday_form.date_to = date(2020, 4, 3)
        with self.assertRaises(ValidationError):
            self.other_public_holiday.write(
                {"date_from": date(2020, 4, 4), "date_to": date(2020, 4, 3)}
            )

        # user sends his request.

        self.public_holiday.with_user(self.user).action_send()

        # check user and user_public_holidays_manager are followers of this request

        self.assertIn(
            self.user_public_holidays_manager.partner_id,
            self.public_holiday.message_partner_ids,
            "Public holidays manager is not added as a request followers.",
        )
        self.assertIn(
            self.user.partner_id,
            self.public_holiday.message_partner_ids,
            "User is not added as a request followers.",
        )

        # check the next activity is correct (activity's name and its assigned to right user)

        self.assertEqual(
            self.public_holiday.activity_type_id.name,
            "Public holiday is ready to be approved",
        )
        self.assertEqual(
            self.public_holiday.activity_ids[0].user_id,
            self.user_public_holidays_manager,
            "Activity should be assigned to Public holidays manager.",
        )

        # check the request has the right stage and state

        self.assertEqual(self.public_holiday.stage_id.name, "Validate")
        self.assertEqual(self.public_holiday.state, "in_progress")

        # accept request by user_manager

        self.public_holiday.with_user(self.user_public_holidays_manager).action_accept()

        # check the name of stage and state.

        self.assertEqual(self.public_holiday.stage_id.name, "Done")
        self.assertEqual(self.public_holiday.state, "done")

        # employee should receive an email notification of approved request
        # todo
        # partners = [
        #     message.user_id.partner_id.id
        #     for message in self.public_holiday.activity_ids
        #     if message.sudo().user_id.partner_id
        # ]
        # self.assertIn(self.employee.user_id.partner_id.id, partners)

        # Test Refuse workflow : refuse other_public_holiday it by Public holidays manager

        # Send the new request with user

        self.other_public_holiday.with_user(self.user).action_send()

        # Refuse request by Public holidays manager

        self.other_public_holiday.with_user(
            self.user_public_holidays_manager
        ).action_refuse()

        # check request has the right stage and state

        self.assertEqual(self.other_public_holiday.stage_id.name, "Refused")
        self.assertEqual(self.other_public_holiday.state, "cancel")

        # User should receive an email notification of refused request
        # todo
        # partners = [
        #     message.user_id.partner_id.id
        #     for message in self.public_holiday.activity_ids
        #     if message.sudo().user_id.partner_id
        # ]
        # self.assertIn(self.employee.user_id.partner_id.id, partners)
