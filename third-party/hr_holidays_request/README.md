# Hr Holidays Request

This Module protects the main menu of module hr_holidays (Time Off) with the group employee officer and changes its
default icon.

**Table of contents**

- [Overview](#overview)
- [Configuration](#configuration)
- [Bug Tracker](#bug-tracker)
- [Maintainer](#maintainer)

## Overview

While trying to install this module or using a backend theme the default icon will be changed like this:

![new icon](static/description/time_off.png)

- This module inherits the original module hr_holidays and integrates module "request" workflow, states will changes to
  the ones of module request.

- The Validation type will by default "hr".

- Any configuration of stages will be within the menu manage stages.

## Configuration

- The user needs to have the access right of employees "officer".
- Go to: setting -> users & companies -> users.
- In access rights of Human ressources -> Employees, select "Officer".

## Bug Tracker

Bugs are tracked on [Gitlab Issues](https://gitlab.com/hadooc/odoo/hr/issues)

In case of trouble, please check there if your issue has already been reported. If you spotted it first, help us smash
it by providing detailed and welcomed feedback.

## Maintainer

![Hadooc](https://hadooc.com/logo)

This module is maintained by Hadooc.

To contribute to this module, please visit [Contributing Page](https://gitlab.com/hadooc/extra/wikis/Contributing).
