from app.services.output_filter import InternalOutputStreamFilter, strip_internal_agent_output


def test_strip_status_report_fenced_block() -> None:
    text = "\n".join(
        [
            "可见回答",
            "```status_report",
            "{",
            '  "state": "completed"',
            "}",
            "```",
            "后续结论",
        ]
    )

    assert strip_internal_agent_output(text) == "可见回答\n后续结论"


def test_strip_partial_streaming_status_report_block() -> None:
    assert strip_internal_agent_output("```") == ""
    assert strip_internal_agent_output("```stat") == ""
    assert strip_internal_agent_output("可见回答\n```status") == "可见回答"


def test_internal_output_stream_filter_only_emits_visible_delta() -> None:
    stream_filter = InternalOutputStreamFilter()

    assert stream_filter.push("可见回答\n") == "可见回答"
    assert stream_filter.push("```") == ""
    assert stream_filter.push("status_report\n") == ""
    assert stream_filter.push('{"state":"completed"}\n') == ""
    assert stream_filter.push("```\n") == ""
    assert stream_filter.push("最终结论") == "\n最终结论"
