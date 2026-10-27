"use client";

/** A Dialog pinned to the bottom edge on phones — see DialogContent variant="sheet". */
export {
  Dialog as Sheet,
  DialogTrigger as SheetTrigger,
  DialogClose as SheetClose,
  DialogHeader as SheetHeader,
  DialogTitle as SheetTitle,
  DialogDescription as SheetDescription,
  DialogFooter as SheetFooter,
} from "./dialog";
import { forwardRef, type ComponentProps } from "react";
import { DialogContent } from "./dialog";

export const SheetContent = forwardRef<
  HTMLDivElement,
  Omit<ComponentProps<typeof DialogContent>, "variant">
>(function SheetContent(props, ref) {
  return <DialogContent ref={ref} variant="sheet" {...props} />;
});
