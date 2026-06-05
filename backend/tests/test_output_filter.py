from app.services.output_filter import InternalOutputStreamFilter, strip_internal_agent_output


def test_strip_status_report_fenced_block() -> None:
    text = "\n".join(
        [
            "visible answer",
            "```status_report",
            "{",
            '  "state": "completed"',
            "}",
            "```",
            "later answer",
        ]
    )

    assert strip_internal_agent_output(text) == "visible answer\nlater answer"


def test_strip_partial_streaming_status_report_block() -> None:
    assert strip_internal_agent_output("```") == ""
    assert strip_internal_agent_output("visible answer\n``") == "visible answer"
    assert strip_internal_agent_output("```stat") == ""
    assert strip_internal_agent_output("visible answer\n``` sta") == "visible answer"
    assert strip_internal_agent_output("visible answer\n```status") == "visible answer"


def test_strip_status_report_fence_with_spacing() -> None:
    text = "\n".join(
        [
            "visible answer",
            "``` status_report",
            '{"state":"completed"}',
            "```",
            "later answer",
        ]
    )

    assert strip_internal_agent_output(text) == "visible answer\nlater answer"


def test_strip_status_fence_alias() -> None:
    text = "\n".join(
        [
            "visible answer",
            "```status",
            '{"state":"completed"}',
            "```",
            "later answer",
        ]
    )

    assert strip_internal_agent_output(text) == "visible answer\nlater answer"


def test_strip_status_report_shaped_generic_fenced_block() -> None:
    text = "\n".join(
        [
            "visible answer",
            "```json",
            '{"state":"completed","will":"complete","confidence":0.95}',
            "```",
            "later answer",
        ]
    )

    assert strip_internal_agent_output(text) == "visible answer\nlater answer"


def test_strip_streaming_bare_fence_status_report_block() -> None:
    assert strip_internal_agent_output("visible answer\n```\nstatus_report") == "visible answer"
    assert (
        strip_internal_agent_output(
            'visible answer\n```\n{"state":"completed","will":"complete"}'
        )
        == "visible answer"
    )


def test_keep_completed_regular_code_block() -> None:
    text = "\n".join(["visible answer", "```python", "print(1)", "```"])

    assert strip_internal_agent_output(text) == text


def test_internal_output_stream_filter_only_emits_visible_delta() -> None:
    stream_filter = InternalOutputStreamFilter()

    assert stream_filter.push("visible answer\n") == "visible answer"
    assert stream_filter.push("``") == ""
    assert stream_filter.push("`status_report\n") == ""
    assert stream_filter.push('{"state":"completed"}\n') == ""
    assert stream_filter.push("```\n") == ""
    assert stream_filter.push("final answer") == "\nfinal answer"


def test_internal_output_stream_filter_hides_bare_fence_status_report() -> None:
    stream_filter = InternalOutputStreamFilter()

    assert stream_filter.push("visible answer\n") == "visible answer"
    assert stream_filter.push("```\n") == ""
    assert stream_filter.push('status_report\n{"state":"completed","will":"complete"}\n') == ""
    assert stream_filter.push("```\n") == ""
    assert stream_filter.push("final answer") == "\nfinal answer"


def test_internal_output_stream_filter_buffers_spaced_status_report_prefix() -> None:
    stream_filter = InternalOutputStreamFilter()

    assert stream_filter.push("visible answer") == "visible answer"
    assert stream_filter.push("\n``` ") == ""
    assert stream_filter.push("sta") == ""
    assert stream_filter.push("tus_report\n") == ""
    assert stream_filter.push('{"state":"completed"}\n') == ""
    assert stream_filter.push("```\n") == ""
    assert stream_filter.push("final answer") == "\nfinal answer"
