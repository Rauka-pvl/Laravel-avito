<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Файловый менеджер</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<div class="container mt-4">
    <h3>Файловый менеджер</h3>

    <p><strong>Текущая папка:</strong> /storage/{{ $relativePath }}</p>

    @if($relativePath)
        <a href="{{ route('storage.view', ['path' => dirname($relativePath)]) }}" class="btn btn-secondary mb-3">
            🔙 Назад
        </a>
    @endif

    <ul class="list-group">
        @foreach($items as $item)
            @php
                $fullPath = $basePath . '/' . $item;
                $isDir = is_dir($fullPath);
                $encodedPath = ltrim($relativePath . '/' . $item, '/');
            @endphp

            <li class="list-group-item d-flex justify-content-between align-items-center">
                @if($isDir)
                    📁 <a href="{{ route('storage.view', ['path' => $encodedPath]) }}">{{ $item }}</a>
                @else
                    📄 <a href="{{ asset('storage/' . $encodedPath) }}" target="_blank">{{ $item }}</a>
                @endif
            </li>
        @endforeach
    </ul>
</div>
</body>
</html>
