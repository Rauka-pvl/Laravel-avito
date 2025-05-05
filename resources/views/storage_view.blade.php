<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Файловый менеджер</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
</head>
<body>
<div class="container mt-5">
    <h2>Содержимое storage</h2>

    @php
        $dir = public_path('storage');
        $items = scandir($dir);
    @endphp

    <ul class="list-group mt-3">
        @foreach($items as $item)
            @if($item !== '.' && $item !== '..')
                @php
                    $path = asset('storage/' . $item);
                    $fullPath = $dir . '/' . $item;
                @endphp

                <li class="list-group-item d-flex justify-content-between align-items-center">
                    @if(is_dir($fullPath))
                        📁 {{ $item }}
                    @else
                        📄 <a href="{{ $path }}" target="_blank">{{ $item }}</a>
                    @endif
                </li>
            @endif
        @endforeach
    </ul>
</div>
</body>
</html>
