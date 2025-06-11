@php
    $prefix = "items[{$index}]";
@endphp

<div class="mb-4">
    <label class="block text-sm text-gray-300">Бренд</label>
    <input name="{{ $prefix }}[brand]" required class="w-full text-black" type="text">
</div>

<div class="mb-4">
    <label class="block text-sm text-gray-300">Артикул</label>
    <input name="{{ $prefix }}[article]" required class="w-full text-black" type="text">
</div>

<div class="mb-4">
    <label class="block text-sm text-gray-300">Описание</label>
    <textarea name="{{ $prefix }}[description]" class="w-full text-black" rows="2"></textarea>
</div>

<div class="mb-4">
    <label class="block text-sm text-gray-300">Бренд на замену</label>
    <input name="{{ $prefix }}[brand_replace]" required class="w-full text-black" type="text">
</div>

<div class="mb-4">
    <label class="block text-sm text-gray-300">Артикул на замену</label>
    <input name="{{ $prefix }}[article_replace]" required class="w-full text-black" type="text">
</div>

<div class="mb-4">
    <label class="block text-sm text-gray-300">Описание добавка</label>
    <textarea name="{{ $prefix }}[description_replace]" class="w-full text-black" rows="2"></textarea>
</div>
