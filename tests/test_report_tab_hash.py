from pathlib import Path


def test_fault_form_action_preserves_report_tab_fragment():
    template = Path("app/templates/index.html").read_text(encoding="utf-8")

    assert 'action="{{ url_for(\'submit_fault\') }}#report-a-fault"' in template
