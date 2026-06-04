import { useEffect } from "react";
import { ArrowLeftOutlined } from "@ant-design/icons";
import {
  App as AntApp,
  Button,
  Card,
  Checkbox,
  Drawer,
  Form,
  Input,
  Space,
  Tabs,
  Typography,
} from "antd";
import { api } from "@/api";
import type { User } from "@/types";
import { ModelSettings } from "../ModelSettings";

const { Text } = Typography;

export function GlobalSettingsDrawer({
  open,
  asPage,
  user,
  onClose,
  onUserUpdated,
}: {
  open?: boolean;
  asPage?: boolean;
  user: User;
  onClose: () => void;
  onUserUpdated: (user: User) => void;
}) {
  const [profileForm] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const { message } = AntApp.useApp();

  useEffect(() => {
    if (!open && !asPage) return;
    profileForm.setFieldsValue({ display_name: user.name });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asPage, open, user.id]);

  const content = (
    <Tabs
        items={[
          {
            key: "account",
            label: "账号",
            children: (
              <div className="workspace-grid">
                <Card title="个人资料">
                  <Form
                    form={profileForm}
                    layout="vertical"
                    onFinish={async (values) => {
                      const updated = await api.updateProfile({
                        display_name: values.display_name,
                      });
                      onUserUpdated(updated);
                      message.success("个人资料已更新");
                    }}
                  >
                    <Form.Item
                      name="display_name"
                      label="显示名称"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Button type="primary" htmlType="submit">
                      保存资料
                    </Button>
                  </Form>
                </Card>
                <Card title="修改密码">
                  <Form
                    form={passwordForm}
                    layout="vertical"
                    onFinish={async (values) => {
                      await api.changePassword({
                        current_password: values.current_password,
                        new_password: values.new_password,
                      });
                      passwordForm.resetFields();
                      message.success("密码已更新");
                    }}
                  >
                    <Form.Item
                      name="current_password"
                      label="当前密码"
                      rules={[{ required: true }]}
                    >
                      <Input.Password />
                    </Form.Item>
                    <Form.Item
                      name="new_password"
                      label="新密码"
                      rules={[{ required: true, min: 6 }]}
                    >
                      <Input.Password />
                    </Form.Item>
                    <Button htmlType="submit">更新密码</Button>
                  </Form>
                </Card>
              </div>
            ),
          },
          {
            key: "models",
            label: "模型 API",
            children: <ModelSettings message={message} user={user} onUserUpdated={onUserUpdated} />,
          },
          {
            key: "general",
            label: "常规",
            children: (
              <Card>
                <Space direction="vertical">
                  <Checkbox defaultChecked>发送消息后自动滚动到底部</Checkbox>
                  <Checkbox defaultChecked>流式回复时显示运行状态</Checkbox>
                  <Checkbox defaultChecked>
                    产物卡片点击后再打开右侧预览
                  </Checkbox>
                </Space>
              </Card>
            ),
          },
        ]}
      />
  );

  return (
    <>
      {asPage ? (
        <div className="page-view">
          <div className="page-header">
            <Button icon={<ArrowLeftOutlined />} onClick={onClose}>返回</Button>
            <Text strong>全局设置</Text>
          </div>
          <div className="page-content">{content}</div>
        </div>
      ) : (
        <Drawer title="全局设置" width={920} open={open} onClose={onClose}>
          {content}
        </Drawer>
      )}
    </>
  );
}
