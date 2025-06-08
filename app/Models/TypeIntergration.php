<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class TypeIntergration extends Model
{
    use HasFactory;

    public function intergrations()
    {
        return $this->hasMany(Intergration::class, 'type_integration', 'id');
    }
    protected $fillable = [
        'name',
        'description',
    ];
}
