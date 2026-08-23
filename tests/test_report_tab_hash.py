from pathlib import Path


def test_fault_submit_button_preserves_report_tab_fragment():
    template = Path("app/templates/index.html").read_text(encoding="utf-8")

    assert 'action="{{ url_for(\'submit_fault\') }}"' in template
    assert 'formaction="{{ url_for(\'submit_fault\') }}#report-a-fault"' in template


def test_validation_summary_is_inside_report_panel():
    template = Path("app/templates/index.html").read_text(encoding="utf-8")

    report_panel = template.index('id="report-a-fault"')
    error_summary = template.index('class="govuk-error-summary"')
    report_heading = template.index('<h2 class="govuk-heading-l">Report a fault</h2>')

    assert report_panel < error_summary < report_heading
