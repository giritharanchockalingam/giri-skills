// Fictional fixture (ui-component-quality evals): shared icon button that always carries an accessible name.
import type { ButtonHTMLAttributes, ReactNode } from "react";

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
};

export function IconButton({ label, children, ...rest }: IconButtonProps) {
  return (
    <button type="button" aria-label={label} className="icon-button" {...rest}>
      {children}
    </button>
  );
}
