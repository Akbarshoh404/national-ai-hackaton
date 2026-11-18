import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center p-5">
      <div className="tile mx-auto w-full max-w-[520px]">
        <h1 className="serif text-[32px]">Bu sahifa topilmadi</h1>
        <p className="mt-2 text-text-2">Manzil o‘zgargan yoki hali qo‘shilmagan.</p>
        <Link href="/" className="btn btn-plain -ml-2 mt-2">
          Bosh sahifaga qaytish
        </Link>
      </div>
    </main>
  );
}
