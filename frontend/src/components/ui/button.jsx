import { forwardRef } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export const Button = forwardRef(function Button({ className, variant = 'default', children, ...props }, ref) {
  return <button ref={ref} className={twMerge(clsx('button', variant === 'outline' && 'button-outline', variant === 'ghost' && 'button-ghost', className))} {...props}>{children}</button>;
});
