import { useState } from "react";
import {
  Button,
  Form,
  Input,
  Segmented,
  Space,
  Typography,
  App as AntApp,
} from "antd";
import { LoginOutlined, ApiOutlined } from "@ant-design/icons";
import { api } from "@/api";
import type { User } from "@/types";

const { Text, Title, Paragraph } = Typography;

export function LoginScreen({ onLogin }: { onLogin: (user: User) => void }) {
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");
  const { message } = AntApp.useApp();

  const submit = async (values: {
    email?: string;
    username?: string;
    display_name?: string;
    password?: string;
  }) => {
    setLoading(true);
    try {
      if (mode === "register") {
        onLogin(
          await api.register({
            email: values.email ?? "",
            username: values.username || values.email?.split("@")[0] || "",
            display_name:
              values.display_name || values.username || values.email,
            password: values.password ?? "",
          }),
        );
        message.success("注册成功，已登录");
      } else {
        onLogin(
          await api.login(
            values.email ?? "demo",
            values.password ?? "agenthub",
          ),
        );
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  const demo = async () => {
    setLoading(true);
    try {
      onLogin(await api.demoLogin());
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-panel">
        <div>
          <Text type="secondary">AgentHub</Text>
          <Title level={1}>IM 多 Agent 工作台</Title>
          <Paragraph>
            登录后进入会话、Agent、文件、知识库和部署一体化协作空间。
          </Paragraph>
        </div>
        <Segmented
          block
          className="login-mode"
          value={mode}
          onChange={(value) => setMode(value as "login" | "register")}
          options={[
            { label: "登录", value: "login" },
            { label: "注册", value: "register" },
          ]}
        />
        <Form key={mode} layout="vertical" onFinish={submit}>
          <Form.Item
            label="Email"
            name="email"
            initialValue={mode === "login" ? "demo" : undefined}
            rules={
              mode === "register"
                ? [{ required: true, type: "email", message: "请输入有效邮箱" }]
                : undefined
            }
          >
            <Input
              size="large"
              prefix={<LoginOutlined />}
              placeholder="demo 或邮箱"
              aria-label="email"
            />
          </Form.Item>
          {mode === "register" && (
            <>
              <Form.Item
                label="用户名"
                name="username"
                rules={[{ required: true, message: "请输入用户名" }]}
              >
                <Input size="large" placeholder="agenthub-user" />
              </Form.Item>
              <Form.Item label="显示名称" name="display_name">
                <Input size="large" placeholder="你的名字" />
              </Form.Item>
            </>
          )}
          <Form.Item
            label="Password"
            name="password"
            initialValue={mode === "login" ? "agenthub" : undefined}
            rules={
              mode === "register"
                ? [{ required: true, min: 6, message: "密码至少 6 位" }]
                : undefined
            }
          >
            <Input.Password
              size="large"
              placeholder="agenthub"
              aria-label="password"
            />
          </Form.Item>
          <Space className="login-actions">
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              loading={loading}
            >
              {mode === "register" ? "注册并登录" : "登录"}
            </Button>
            <Button
              size="large"
              icon={<ApiOutlined />}
              onClick={demo}
              loading={loading}
              data-testid="demo-login"
              disabled={mode === "register"}
            >
              演示用户
            </Button>
          </Space>
        </Form>
      </section>
    </main>
  );
}
