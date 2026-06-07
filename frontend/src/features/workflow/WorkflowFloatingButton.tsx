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
  testId,
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
  testId?: string;
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
          data-testid={testId}
          onPointerDown={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            onClick();
          }}
        />
      </Badge>
    </Tooltip>
  );
}
