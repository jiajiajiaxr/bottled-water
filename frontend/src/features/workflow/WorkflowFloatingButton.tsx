import { Badge, Button, Tooltip } from "antd";
import type { ReactNode } from "react";

export function WorkflowFloatingButton({
  title,
  icon,
  active,
  disabled,
  danger,
  loading,
  badgeCount,
  placement = "right",
  onClick,
}: {
  title: string;
  icon: ReactNode;
  active?: boolean;
  disabled?: boolean;
  danger?: boolean;
  loading?: boolean;
  badgeCount?: number;
  placement?: "left" | "right";
  onClick: () => void;
}) {
  return (
    <Tooltip title={title} placement={placement}>
      <Badge count={badgeCount} size="small" offset={[-2, 2]}>
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
      </Badge>
    </Tooltip>
  );
}
