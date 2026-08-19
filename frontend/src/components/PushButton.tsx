import type { ButtonHTMLAttributes, ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";

type PushButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "onDrag" | "onDragStart" | "onDragEnd" | "onAnimationStart" | "onAnimationEnd" | "onAnimationIteration"
> & {
  variant?: "primary" | "soft" | "outline" | "matte";
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
  const reduceMotion = useReducedMotion();
  const classes = [
    "btn",
    variant === "soft" ? "btn--soft" : "",
    variant === "outline" ? "btn--outline" : "",
    variant === "matte" ? "btn--matte" : "",
    size === "sm" ? "btn--sm" : "",
    size === "lg" ? "btn--lg" : "",
    loading ? "is-loading" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <motion.button
      type={type}
      className={classes}
      disabled={disabled || loading}
      whileHover={reduceMotion || disabled || loading ? undefined : { y: -1 }}
      whileTap={reduceMotion || disabled || loading ? undefined : { scale: 0.98 }}
      transition={{ duration: 0.15 }}
      {...rest}
    >
      <span className="btn__label">{children}</span>
    </motion.button>
  );
}
