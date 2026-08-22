import { cn } from "@/lib/utils";

export default function Logo({ className }) {
  return <img src="/qidian-rehearsal-icon.png" alt="奇点排练 Agent" className={cn("shrink-0 block object-cover", className)} />;
}
