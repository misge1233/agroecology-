import type { HTMLAttributes, ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const alertVariants = cva("flex gap-3 rounded-card border p-4 text-sm", {
  variants: {
    variant: {
      info: "border-accent/40 bg-accent-soft text-text",
      success: "border-success/40 bg-success-soft text-text",
      warning: "border-warning/50 bg-warning-soft text-text",
      // Danger = system errors only (never low confidence).
      danger: "border-danger/40 bg-danger-soft text-text",
    },
  },
  defaultVariants: { variant: "info" },
});

const ICONS = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
};
const ICON_COLOR = {
  info: "text-accent-text",
  success: "text-success-text",
  warning: "text-warning-text",
  danger: "text-danger-text",
};

export interface AlertProps
  extends Omit<HTMLAttributes<HTMLDivElement>, "title">,
    VariantProps<typeof alertVariants> {
  /** Bold first line (a node, not the native tooltip attribute). */
  title?: ReactNode;
  children?: ReactNode;
}

export function Alert({ className, variant = "info", title, children, ...props }: AlertProps) {
  const v = variant ?? "info";
  const Icon = ICONS[v];
  return (
    <div
      role={v === "danger" || v === "warning" ? "alert" : "status"}
      className={cn(alertVariants({ variant: v }), className)}
      {...props}
    >
      <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", ICON_COLOR[v])} aria-hidden />
      <div className="min-w-0 flex-1">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className={cn(title && "mt-1", "text-muted")}>{children}</div> : null}
      </div>
    </div>
  );
}
