import type { ButtonHTMLAttributes, ReactNode } from "react";

type PushButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "soft" | "outline";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  children: ReactNode;
};

export function PushButton({
  variant = "primary",
  size = "md",
  loading = false,
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
      {...rest}
    >
      <span className="btn__label">{children}</span>
    </button>
  );
}
