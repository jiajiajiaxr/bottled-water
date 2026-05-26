import { Button, Tooltip } from "antd";
import type { ReactNode } from "react";

export function WorkflowFloatingButton({
  title,
  icon,
  active,
  disabled,
  danger,
  loading,
  placement = "right",
  onClick,
}: {
  title: string;
  icon: ReactNode;
  active?: boolean;
  disabled?: boolean;
  danger?: boolean;
  loading?: boolean;
  placement?: "left" | "right";
  onClick: () => void;
}) {
  return (
    <Tooltip title={title} placement={placement}>
      <Button
        aria-label={title}
        shape="circle"
        type={active ? "primary" : "default"}
        danger={danger}
        disabled={disabled}
        loading={loading}
        icon={icon}
        onClick={onClick}
      />
    </Tooltip>
  );
}
