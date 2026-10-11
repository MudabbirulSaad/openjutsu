import * as Dialog from "@radix-ui/react-dialog";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { X } from "lucide-react";
export const cn = (...values: Parameters<typeof clsx>) =>
  twMerge(clsx(...values));
const buttons = cva("button", {
  variants: {
    variant: {
      primary: "button-primary",
      secondary: "button-secondary",
      ghost: "button-ghost",
      danger: "button-danger",
    },
    size: { normal: "", small: "button-small", icon: "button-icon" },
  },
  defaultVariants: { variant: "secondary", size: "normal" },
});
export function Button({
  className,
  variant,
  size,
  asChild,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttons> & { asChild?: boolean }) {
  const Component = asChild ? Slot : "button";
  return (
    <Component
      className={cn(buttons({ variant, size }), className)}
      {...props}
    />
  );
}
export function Sheet({
  title,
  trigger,
  children,
}: {
  title: string;
  trigger: ReactNode;
  children: ReactNode;
}) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="sheet-overlay" />
        <Dialog.Content className="sheet">
          <div className="sheet-heading">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close asChild>
              <Button size="icon" variant="ghost" aria-label="Close inspector">
                <X size={18} />
              </Button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            Clip settings and available actions
          </Dialog.Description>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
