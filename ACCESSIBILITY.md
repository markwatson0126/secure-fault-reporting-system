# Accessibility review and testing

This document records the accessibility work undertaken on the Secure Fault Reporting and Resolution System after completing accessibility-focused continuing professional development (CPD).

The application uses GOV.UK Frontend as a foundation, but this is not treated as evidence that the complete service is accessible. Accessibility depends on how components are combined, the content and interaction design, and how the service is tested and maintained.

## Baseline findings

The existing application already included several useful accessibility foundations:

- page language and descriptive page titles
- a skip link and semantic main landmark
- semantic headings, labels and native form controls
- GOV.UK error summaries and field-level errors in account journeys
- autocomplete attributes for account fields
- text labels as well as colour for fault status
- semantic summary lists for fault details

The review also identified areas for improvement:

- the fault-reporting form was hidden inside a disclosure even though reporting a fault is a core task
- fault-reporting validation returned plain HTTP error text instead of accessible, contextual form errors
- fault actions had repeated names such as `Mark as closed` and `Delete fault` without additional context for assistive technology
- closing and deleting faults did not provide an accessible confirmation step
- successful fault actions did not provide explicit confirmation
- the account and administration links were not contained in a navigation landmark
- the email-domain table lacked a caption and explicit column scopes
- the faults page did not initially group active, reporting and closed-fault tasks clearly enough
- active and closed faults were intermingled by creation date even though reviewing active faults before reporting can help avoid duplicate reports
- accessibility was not represented in automated tests as part of continuous integration
- no formal accessibility audit or disabled-user research had been completed

## Changes implemented

The accessibility improvement branch makes the following changes:

1. The fault-reporting task has been removed from a `details` disclosure and placed in an explicit GOV.UK Tabs interface alongside `Active faults` and `Closed faults`.
2. `Active faults` is the default tab so users can review current issues before reporting a possible duplicate.
3. The fault-reporting tab becomes the selected and visible panel when server-side validation errors occur, so error messages and preserved values are not hidden from the user.
4. Fault-reporting validation now redisplays the page with an error summary, field-level messages, programmatic error associations and preserved user input.
5. Successful reporting, closing and deletion actions display GOV.UK notification banners.
6. Repeated actions include visually hidden contextual text so assistive technology can distinguish which fault or domain the action applies to.
7. Closing and deleting faults use dedicated confirmation pages rather than relying on immediate or JavaScript-only destructive actions.
8. The service uses the GOV.UK Frontend Generic header component markup and an explicit navigation landmark for account and administration links.
9. The redundant `Faults` navigation link is omitted for standard users who have no other service area to navigate to, while it remains available to administrators who move between faults and administration pages.
10. The email-domain table now includes a descriptive caption and `scope="col"` on its headers.
11. A transparent in-service accessibility and testing page records the current approach and limitations.
12. Automated tests cover selected accessibility-related structure and behaviour and therefore run as part of the existing pytest continuous-integration step.

## Manual testing completed so far

WAVE was used on the standard-user faults page. The initial revised page returned zero errors and zero contrast errors, with one redundant-link alert. Manual review identified that the `Faults` navigation link was unnecessary for a standard user because the service title already returned to the only available functional page. The link was therefore removed for standard users while retained for administrators.

The Web Developer document outline and keyboard navigation were then used to review page structure. Although the original revised page was not reported as an automated accessibility error, navigating it prompted a review of whether the information architecture was clear enough for both sighted and assistive-technology users.

Static fault information has deliberately not been added to the tab order because ordinary text should not become an unnecessary keyboard stop. Instead, faults retain semantic headings and summary-list markup, while keyboard focus is reserved for interactive controls. The page now uses the GOV.UK Tabs component so users can switch between active faults, reporting and closed faults without showing all three sections at once.

A keyboard-only retest of the tabbed faults page was completed after the redesign. Focus was visibly indicated, the active tab could be changed with the Left and Right Arrow keys, Tab moved into the currently displayed panel, the `Report a fault` controls followed a logical order (Title, Description, Regional centre, Submit fault), hidden tab panels did not enter the tab sequence, and no keyboard trap was observed.

WAVE was repeated after the final navigation and tab changes. The current standard-user faults page returned zero errors, zero contrast errors and zero alerts, with an AIM score of 10 out of 10. This improves on the earlier result by removing the redundant-link alert. The result is treated as evidence that no automatically detectable WAVE issues were present on the tested page, not as proof of full accessibility or WCAG conformance.

## Manual testing still to perform

Automated checks should be supplemented by further manual testing. The following checks are recommended for the assessment evidence:

- test the fault form with validation errors and confirm that the reporting tab remains visible and the error summary receives focus when GOV.UK Frontend JavaScript is active
- zoom browser content to 200% and 400% and check for loss of content or horizontal scrolling where avoidable
- re-check headings and landmarks after the tab change
- use Web Developer to inspect document structure
- use a colour contrast analyser for custom colours
- where practical, test core journeys with a screen reader

## Limits of the evidence

Passing automated checks is not proof of accessibility. Automated tools cannot assess all WCAG requirements and cannot reproduce the experience of disabled users.

This demonstration application has not yet had a formal accessibility audit or usability testing with disabled users. It must therefore not be described as fully accessible or WCAG compliant. A production service would also require a monitored accessibility feedback route, ongoing review of relevant standards and framework updates, and accessibility responsibilities embedded across design, development, testing and procurement.
