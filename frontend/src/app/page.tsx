import { redirect } from "next/navigation";

export default function Home() {
  // We'll redirect the root to the playground since it's the primary interface
  redirect("/playground");
}
