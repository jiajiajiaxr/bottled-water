from __future__ import annotations


TOOLBOXES = {
    "master": [
        "file.extract_text",
        "file.summarize",
        "file.embed",
        "artifact.preview",
        "artifact.export",
        "db.inspect",
        "api.test",
        "security.audit",
    ],
    "frontend": ["file.read", "file.write", "artifact.create_web_app", "sandbox.run", "browser.preview"],
    "backend": ["file.read", "file.write", "db.inspect", "sandbox.run", "api.test"],
    "reviewer": ["artifact.diff", "test.run", "security.audit", "document.review"],
    "deploy": ["artifact.export", "deploy.preview", "deploy.rollback", "sandbox.run"],
    "writing": [
        "file.extract_text",
        "file.summarize",
        "artifact.create_pdf",
        "artifact.create_docx",
        "artifact.create_pptx",
        "document.review",
    ],
    "chat": ["file.extract_text", "file.preview", "file.summarize"],
}


def get_official_toolbox(agent_type: str) -> list[str]:
    return TOOLBOXES.get(agent_type, TOOLBOXES["chat"])
