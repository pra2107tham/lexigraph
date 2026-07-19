import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[11px] leading-4",
  {
    variants: {
      variant: {
        default: "border-transparent bg-counsel text-paper",
        bronze: "border-bronze/40 bg-bronze/10 text-bronze",
        alert: "border-alert/40 bg-alert/10 text-alert",
        outline: "border-border text-ink-soft",
        live: "border-transparent bg-emerald-live/15 text-counsel",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
