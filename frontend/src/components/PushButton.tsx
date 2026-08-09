import type { ButtonHTMLAttributes, ReactNode } from "react";

type PushButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "push" | "soft" | "outline";
  color?: "pear" | "coral" | "cyan" | "mint" | "ink";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  state?: "default" | "error" | "success";
  children: ReactNode;
};

export function PushButton({
  variant = "push",
  color = "pear",
  size = "md",
  loading = false,
  state = "default",
  className = "",
  children,
  disabled,
  type = "button",
  ...rest
}: PushButtonProps) {
  const classes = [
    "btn",
    variant === "soft" ? "btn--soft" : "",
    variant === "outline" ? "btn--outline" : "",
    color ? `btn--${color}` : "",
    size === "sm" ? "btn--sm" : "",
    size === "lg" ? "btn--lg" : "",
    loading ? "is-loading" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || loading}
      data-state={loading ? "loading" : state === "default" ? undefined : state}
      {...rest}
    >
      <span className="btn__label">{children}</span>
    </button>
  );
}
