<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Intergration extends Model
{
    use HasFactory;
    protected $fillable = [
        'type_integration',
        'brand',
        'article',
        'description',
        'brand_replace',
        'article_replace',
        'description_replace',
    ];
}
