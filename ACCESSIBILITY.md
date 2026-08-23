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
- the faults page did not group active and closed faults under clear section headings, and individual fault titles sat at the same heading level as the reporting task
- active and closed faults were intermingled by creation date even though reviewing active faults before reporting can help avoid duplicate reports
- accessibility was not represented in automated tests as part of continuous integration
- no formal accessibility audit or disabled-user research had been completed

## Changes implemented

The accessibility improvement branch makes the following changes:

1. The fault-reporting form is now visible as a primary task rather than being placed inside a `details` disclosure.
2. Fault-reporting validation now redisplays the page with an error summary, field-level messages, programmatic error associations and preserved user input.
3. Successful reporting, closing and deletion actions display GOV.UK notification banners.
4. Repeated actions include visually hidden contextual text so assistive technology can distinguish which fault or domain the action applies to.
5. Closing and deleting faults use dedicated confirmation pages rather than relying on immediate or JavaScript-only destructive actions.
6. The service uses the GOV.UK Frontend Generic header component markup and an explicit navigation landmark for account and administration links.
7. The email-domain table now includes a descriptive caption and `scope="col"` on its headers.
8. A transparent in-service accessibility and testing page records the current approach and limitations.
9. Automated tests cover selected accessibility-related structure and behaviour and therefore run as part of the existing pytest continuous-integration step.
10. The faults page now uses a clearer information hierarchy: `Faults` as the H1, on-page links to `Active faults`, `Report a fault` and `Closed faults`, H2 section headings, and H3 headings for individual faults. Active faults are presented first so users can review current issues before submitting a new report.

## Manual testing completed so far

Initial manual review used the browser keyboard and the Web Developer document outline. The original revised page had one H1 followed by `Report a fault` and every individual fault as H2 headings. Although this was not an automated accessibility error, navigating the page prompted a review of whether the structure communicated the service clearly enough.

Static fault information has deliberately not been added to the tab order because ordinary text should not become an unnecessary keyboard stop. Instead, the page structure has been improved so assistive-technology users can navigate faults by headings and sections, while keyboard focus remains reserved for interactive controls.

## Manual testing still to perform

Automated checks should be supplemented by further manual testing. The following checks are recommended for the assessment evidence:

- complete the main journeys using only the keyboard
- confirm that focus is visible and follows a logical order
- test the fault form with validation errors and confirm that the error summary receives focus when GOV.UK Frontend JavaScript is active
- zoom browser content to 200% and 400% and check for loss of content or horizontal scrolling where avoidable
- re-check headings and landmarks after the information-hierarchy change
- use WAVE to identify automatically detectable issues
- use Web Developer to inspect document structure
- use a colour contrast analyser for custom colours
- where practical, test core journeys with a screen reader

## Limits of the evidence

Passing automated checks is not proof of accessibility. Automated tools cannot assess all WCAG requirements and cannot reproduce the experience of disabled users.

This demonstration application has not yet had a formal accessibility audit or usability testing with disabled users. It must therefore not be described as fully accessible or WCAG compliant. A production service would also require a monitored accessibility feedback route, ongoing review of relevant standards and framework updates, and accessibility responsibilities embedded across design, development, testing and procurement.
